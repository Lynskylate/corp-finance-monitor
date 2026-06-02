import os
import shutil
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass

from tests.conftest import SRC  # noqa: F401
from corp_finance_monitor.core.config import (
    Config,
    EngineConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource


@dataclass
class _RegistryEntry:
    code: str
    org_id: str


class _FakeRegistry:
    def __init__(self, stocks):
        self._stocks = stocks

    def get_a_shares(self):
        return list(self._stocks)


class _BatchingCninfoSource(AbstractSource):
    def __init__(self, name, config):
        super().__init__(name, config)
        self.discover_calls = []
        self._registry = _FakeRegistry(
            [
                _RegistryEntry(code=f"{i:06d}", org_id=f"org{i:06d}")
                for i in range(1, 6)
            ]
        )

    def _get_registry(self):
        return self._registry

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        codes = list(only_stock_codes or [])
        self.discover_calls.append(codes)
        refs = []
        for code in codes:
            refs.append(
                FilingRef(
                    source="cninfo",
                    source_id=f"discover-{code}",
                    stock_code=code,
                    title=f"{code} annual",
                    kind=FilingKind.ANNUAL,
                    published_at="2025-01-01",
                    url=f"https://example.com/{code}.pdf",
                )
            )
        return refs

    def fetch(self, ref):
        return Filing(ref=ref, content=b"%PDF-1.4\nbatching\n")


class _TimingSource(AbstractSource):
    def __init__(self, name, config):
        super().__init__(name, config)
        self.fetch_started = []
        self.fetch_completed = []
        self.max_inflight = 0
        self._inflight = 0
        self._lock = threading.Lock()

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        return [
            FilingRef(
                source="fake",
                source_id=f"fake-{idx}",
                stock_code=f"{idx:06d}",
                title=f"Filing {idx}",
                kind=FilingKind.ANNUAL,
                published_at="2025-01-01",
                url=f"https://example.com/{idx}.pdf",
            )
            for idx in range(3)
        ]

    def fetch(self, ref):
        start = time.monotonic()
        with self._lock:
            self._inflight += 1
            self.max_inflight = max(self.max_inflight, self._inflight)
        self.fetch_started.append(start)
        time.sleep(0.05)
        finish = time.monotonic()
        self.fetch_completed.append(finish)
        with self._lock:
            self._inflight -= 1
        return Filing(ref=ref, content=b"%PDF-1.4\ntiming\n")


class _SerialSource(AbstractSource):
    def __init__(self, name, config):
        super().__init__(name, config)
        self.fetch_started = []
        self.fetch_completed = []

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        return [
            FilingRef(
                source="fake",
                source_id=f"serial-{idx}",
                stock_code=f"{idx:06d}",
                title=f"Serial {idx}",
                kind=FilingKind.ANNUAL,
                published_at="2025-01-01",
                url=f"https://example.com/{idx}.pdf",
            )
            for idx in range(3)
        ]

    def fetch(self, ref):
        start = time.monotonic()
        self.fetch_started.append(start)
        time.sleep(0.01)
        finish = time.monotonic()
        self.fetch_completed.append(finish)
        return Filing(ref=ref, content=b"%PDF-1.4\nserial\n")


class EngineConcurrencyTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_engine_phase2_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _new_config(self, source_name, options=None, concurrency=1, delay=0.0):
        return Config(
            engine=EngineConfig(
                run_once=True,
                interval_minutes=360,
                concurrency=concurrency,
                fetch_delay_seconds=delay,
            ),
            storage=StorageConfig(
                backend="disk",
                base_dir=os.path.join(self.tmpdir, "data"),
            ),
            state_store=StateStoreConfig(
                backend="sqlite",
                path=os.path.join(self.tmpdir, "data", ".cfm_state", "state.db"),
            ),
            sources={
                source_name: SourceConfig(
                    name=source_name,
                    watchlist=[],
                    options=options or {},
                )
            },
        )

    def test_full_market_discover_batches_stock_codes(self):
        cfg = self._new_config(
            "cninfo",
            options={"full_market": True, "full_market_batch_size": 2},
            concurrency=3,
            delay=0,
        )
        engine = Engine(cfg, {"cninfo": _BatchingCninfoSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            self.assertEqual(stats["discovered"], 5)
            self.assertEqual(stats["fetched"], 5)
            source = engine.sources["cninfo"]
            self.assertEqual(source.discover_calls, [["000001", "000002"], ["000003", "000004"], ["000005"]])
        finally:
            engine.close()

    def test_parallel_fetch_honors_concurrency_and_rate_limit(self):
        cfg = self._new_config("fake", concurrency=3, delay=0.05)
        engine = Engine(cfg, {"fake": _TimingSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            source = engine.sources["fake"]
            self.assertEqual(stats, {"discovered": 3, "fetched": 3, "failed": 0})
            self.assertGreaterEqual(source.max_inflight, 2)
            gaps = [
                later - earlier
                for earlier, later in zip(
                    sorted(source.fetch_started),
                    sorted(source.fetch_started)[1:],
                )
            ]
            self.assertEqual(len(gaps), 2)
            for gap in gaps:
                self.assertGreaterEqual(gap, 0.045)
        finally:
            engine.close()

    def test_concurrency_one_preserves_serial_behavior(self):
        cfg = self._new_config("fake", concurrency=1, delay=0.03)
        engine = Engine(cfg, {"fake": _SerialSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            source = engine.sources["fake"]
            self.assertEqual(stats, {"discovered": 3, "fetched": 3, "failed": 0})
            self.assertEqual(len(source.fetch_started), 3)
            self.assertGreaterEqual(
                source.fetch_started[1] - source.fetch_completed[0],
                0.025,
            )
            self.assertGreaterEqual(
                source.fetch_started[2] - source.fetch_completed[1],
                0.025,
            )
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
