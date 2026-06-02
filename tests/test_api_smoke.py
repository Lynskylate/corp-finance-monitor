"""
HTTP API smoke tests for corp-finance-monitor.

We start a uvicorn server (backed by FastAPI) in a background thread against
an empty config (no real sources). Then we exercise every endpoint:

- GET  /healthz
- GET  /api/filings       (empty)
- POST /api/subscriptions (create)
- GET  /api/subscriptions (list)
- POST /api/sync          (with no real sources should be a no-op)
- GET  /api/runs          (list runs)
- GET  /api/filings/<source>/<source_id>  (404)
- GET  /api/filings/<source>/<source_id>  (200 after direct DiskStorage.write)
- GET  /api/unknown       (404)
- POST /api/sync          (CONFLICT when re-entered while first holds the lock)

We also exercise the engine's HTTP layer end-to-end with one fake
"disk" source adapter that records a single deterministic filing.
"""
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

import uvicorn

from tests.conftest import SRC  # noqa: F401
from corp_finance_monitor.core import Config
from corp_finance_monitor.core.config import (
    EngineConfig, StorageConfig, StateStoreConfig, APIConfig, SourceConfig,
)
from corp_finance_monitor.core.model import FilingRef, Filing, FilingKind
from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.api import create_app


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_get(url: str, timeout: float = 5.0):
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _http_post(url: str, body: dict | None = None, timeout: float = 10.0):
    data = json.dumps(body or {}).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


class _FakeSource(AbstractSource):
    """Source that returns one deterministic filing, no network."""

    def discover(self, watchlist=None, since=None):
        ref = FilingRef(
            source="fake",
            source_id="fake-001",
            stock_code="000725",
            stock_name="FAKE CO",
            title="2025年年度报告",
            kind=FilingKind.ANNUAL,
            published_at="2025-04-01",
            url="",
        )
        return [ref]

    def fetch(self, ref):
        return Filing(ref=ref, content=b"%PDF-1.4\nfake pdf body\n")


class _ServerBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cfm_api_test_")
        port = _free_port()
        cfg = Config(
            engine=EngineConfig(run_once=True, interval_minutes=360, fetch_delay_seconds=0),
            storage=StorageConfig(backend="disk", base_dir=os.path.join(cls.tmp, "data")),
            state_store=StateStoreConfig(
                backend="sqlite",
                path=os.path.join(cls.tmp, "data", ".cfm_state", "state.db"),
            ),
            api=APIConfig(host="127.0.0.1", port=port, enabled=True),
            sources={
                "fake": SourceConfig(name="fake", watchlist=[{"stock": "000725"}]),
            },
        )
        cls.app = create_app(cfg, {"fake": _FakeSource})
        cls.port = port
        cls.base = f"http://127.0.0.1:{port}"

        config = uvicorn.Config(
            app=cls.app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
        cls._uvicorn_server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls._uvicorn_server.run, daemon=True)
        cls.thread.start()
        cls._wait_ready(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls._uvicorn_server.should_exit = True
        cls.thread.join(timeout=5)
        engine = cls.app.state.engine
        try:
            engine.close()
        except Exception:
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _wait_ready(base: str, timeout: float = 5.0):
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                with urlrequest.urlopen(base + "/healthz", timeout=1):
                    return
            except URLError as e:
                last_err = e
                time.sleep(0.05)
        raise RuntimeError(f"server not ready: {last_err}")

    @property
    def engine(self):
        return self.app.state.engine


class TestHealthAndNotFound(_ServerBase):
    def test_healthz(self):
        status, body = _http_get(self.base + "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})

    def test_unknown_route_404(self):
        status, body = _http_get(self.base + "/api/unknown")
        self.assertEqual(status, 404)

    def test_filing_detail_404(self):
        status, body = _http_get(self.base + "/api/filings/fake/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(body.get("detail"), "filing_not_found")


class TestFilingsEndpoint(_ServerBase):
    def test_filings_limit_offset_uses_storage_pagination(self):
        refs = [
            FilingRef(
                source="page-test",
                source_id=f"page-{idx:03d}",
                stock_code="000725",
                stock_name="FAKE CO",
                title=f"2025年第{idx}条公告",
                kind=FilingKind.ANNUAL,
                published_at=f"2025-04-{idx:02d}",
                url="",
            )
            for idx in range(1, 6)
        ]
        for ref in refs:
            self.engine.storage.upsert_metadata(ref)

        status, body = _http_get(self.base + "/api/filings?source=page-test&limit=2&offset=1")
        self.assertEqual(status, 200)
        items = body.get("items", [])
        self.assertEqual(len(items), 2)
        self.assertEqual(body.get("total"), 5)
        self.assertEqual(body.get("limit"), 2)
        self.assertEqual(body.get("offset"), 1)
        self.assertEqual(
            [item["source_id"] for item in items],
            ["page-004", "page-003"],
        )

    def test_filings_empty_initially(self):
        # Other tests in this class may have inserted fake source records.
        # We just assert the endpoint responds with a JSON list of items.
        status, body = _http_get(self.base + "/api/filings?source=__nonexistent__")
        self.assertEqual(status, 200)
        self.assertIsInstance(body.get("items"), list)
        self.assertEqual(body.get("items"), [])

    def test_filings_after_manual_store(self):
        # Insert a record directly via the engine's storage, then list it.
        ref = FilingRef(
            source="fake",
            source_id="manual-001",
            stock_code="000725",
            stock_name="FAKE CO",
            title="2025年第一季度报告",
            kind=FilingKind.Q1,
            published_at="2025-04-25",
            url="",
        )
        filing = Filing(ref=ref, content=b"%PDF-1.4\nbody\n")
        self.engine.storage.store(filing)

        status, body = _http_get(self.base + "/api/filings?source=fake&stock_code=000725")
        self.assertEqual(status, 200)
        items = body.get("items", [])
        self.assertGreaterEqual(len(items), 1)
        ids = {it["source_id"] for it in items}
        self.assertIn("manual-001", ids)

    def test_filing_detail_200(self):
        ref = FilingRef(
            source="fake",
            source_id="manual-002",
            stock_code="000725",
            stock_name="FAKE CO",
            title="2025年半年度报告",
            kind=FilingKind.SEMI,
            published_at="2025-08-25",
            url="",
        )
        self.engine.storage.store(Filing(ref=ref, content=b"x"))

        status, body = _http_get(self.base + "/api/filings/fake/manual-002")
        self.assertEqual(status, 200)
        self.assertIn("filing", body)
        self.assertIn("stored_path", body)
        self.assertEqual(body["filing"]["source_id"], "manual-002")
        self.assertEqual(body["filing"]["kind"], "semi")


class TestSubscriptionsEndpoint(_ServerBase):
    def test_subscription_create_and_list(self):
        payload = {
            "name": "boe-annual",
            "source": "cninfo",
            "stock_code": "000725",
            "kind": "annual",
            "target": "https://example.com/webhook",
        }
        status, body = _http_post(self.base + "/api/subscriptions", payload)
        self.assertEqual(status, 201)
        sub = body.get("subscription", {})
        self.assertEqual(sub.get("name"), "boe-annual")
        self.assertTrue(sub.get("active"))
        self.assertIsInstance(sub.get("id"), int)

        # list
        status, body = _http_get(self.base + "/api/subscriptions?active_only=true")
        self.assertEqual(status, 200)
        names = [s["name"] for s in body.get("items", [])]
        self.assertIn("boe-annual", names)

    def test_subscription_create_requires_name(self):
        status, body = _http_post(self.base + "/api/subscriptions", {"source": "cninfo"})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("detail"), "name_required")

    def test_subscription_create_rejects_invalid_json(self):
        data = b"this is not json"
        req = urlrequest.Request(
            self.base + "/api/subscriptions",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as ctx:
            urlrequest.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)


class TestRunsEndpoint(_ServerBase):
    def test_runs_after_sync(self):
        # /api/sync against an empty source should be a fast no-op.
        status, body = _http_post(self.base + "/api/sync", {"sources": ["fake"]})
        self.assertEqual(status, 200)
        self.assertIn("stats", body)
        stats = body["stats"]
        self.assertIn("discovered", stats)
        self.assertIn("fetched", stats)
        self.assertIn("failed", stats)

        status, body = _http_get(self.base + "/api/runs?limit=5")
        self.assertEqual(status, 200)
        items = body.get("items", [])
        self.assertGreaterEqual(len(items), 1)
        # Most-recent-first ordering
        ids = [r["id"] for r in items]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_runs_limit(self):
        # Insert several runs via direct call
        for i in range(5):
            self.engine.state_store.record_run(
                f"2025-06-0{i + 1}T00:00:00",
                f"2025-06-0{i + 1}T00:01:00",
                discovered=1, fetched=1, failed=0,
            )
        status, body = _http_get(self.base + "/api/runs?limit=3")
        self.assertEqual(status, 200)
        self.assertEqual(len(body.get("items", [])), 3)


class TestSyncLocking(_ServerBase):
    def test_concurrent_sync_returns_409(self):
        # Patch Engine.run_once to slow down so the second request hits the
        # run_lock held by the first one and gets a 409.
        from corp_finance_monitor.core.engine import Engine as EngineCls
        original = EngineCls.run_once
        started = threading.Event()
        proceed = threading.Event()

        def slow_run_once(self, selected_sources=None, since=None, resume=False, tier=None):
            started.set()
            proceed.wait(timeout=5)
            return {"discovered": 0, "fetched": 0, "failed": 0}

        EngineCls.run_once = slow_run_once  # type: ignore[assignment]
        try:
            results: dict = {}

            def first():
                results["first"] = _http_post(
                    self.base + "/api/sync", {"sources": ["fake"]}, timeout=10,
                )

            def second():
                # Give the first request a head start
                started.wait(timeout=5)
                results["second"] = _http_post(
                    self.base + "/api/sync", {"sources": ["fake"]}, timeout=10,
                )

            t1 = threading.Thread(target=first)
            t2 = threading.Thread(target=second)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
            proceed.set()

            self.assertEqual(results.get("first", (None,))[0], 200)
            self.assertEqual(results.get("second", (None,))[0], 409)
            self.assertEqual(
                results["second"][1].get("detail"),
                "sync_already_running",
            )
        finally:
            EngineCls.run_once = original  # type: ignore[assignment]


class TestSyncEndToEnd(_ServerBase):
    def test_sync_invokes_fake_source_and_persists(self):
        before = self.engine.storage.list_refs(source="fake")
        before_ids = {r.source_id for r in before}

        status, body = _http_post(self.base + "/api/sync", {"sources": ["fake"]})
        self.assertEqual(status, 200)
        stats = body.get("stats", {})
        self.assertEqual(stats.get("discovered"), 1)
        self.assertEqual(stats.get("fetched"), 1)
        self.assertEqual(stats.get("failed"), 0)

        after = self.engine.storage.list_refs(source="fake")
        after_ids = {r.source_id for r in after}
        self.assertIn("fake-001", after_ids)
        self.assertNotIn("fake-001", before_ids)


if __name__ == "__main__":
    unittest.main()
