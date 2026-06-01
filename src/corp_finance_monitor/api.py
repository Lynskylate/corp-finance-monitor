from __future__ import annotations
import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from corp_finance_monitor.core import Config, Engine, FilingKind
from corp_finance_monitor.core.model import Subscription

logger = logging.getLogger("cfm.api")


def create_app(config: Config, source_registry: Dict[str, type]) -> ThreadingHTTPServer:
    engine = Engine(config, source_registry)
    engine.initialize()
    run_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "corp-finance-monitor/0.1"

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                return self._json(HTTPStatus.OK, {"ok": True})
            if parsed.path == "/api/filings":
                return self._handle_filings(parsed)
            if parsed.path == "/api/runs":
                return self._handle_runs(parsed)
            if parsed.path == "/api/subscriptions":
                return self._handle_subscriptions_list(parsed)
            if parsed.path.startswith("/api/filings/"):
                return self._handle_filing_detail(parsed.path)
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/sync":
                return self._handle_sync()
            if parsed.path == "/api/subscriptions":
                return self._handle_subscription_create()
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def log_message(self, fmt: str, *args):
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _handle_filings(self, parsed):
            qs = parse_qs(parsed.query)
            kind = qs.get("kind", [None])[0]
            try:
                limit = int(qs.get("limit", ["50"])[0])
                offset = int(qs.get("offset", ["0"])[0])
            except ValueError:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "limit_offset_must_be_int"})
            if limit < 0 or offset < 0:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "limit_offset_must_be_non_negative"})
            refs = engine.storage.list_refs(
                source=qs.get("source", [None])[0],
                stock_code=qs.get("stock_code", [None])[0],
                kind=FilingKind(kind) if kind else None,
                since=qs.get("since", [None])[0],
            )
            total = len(refs)
            items = refs[offset: offset + limit] if limit else refs[offset:]
            return self._json(
                HTTPStatus.OK,
                {
                    "items": [serialize_ref(ref) for ref in items],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
            )

        def _handle_filing_detail(self, path: str):
            parts = path.split("/")
            if len(parts) < 5:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_path"})
            _, _, _, source, source_id = parts[:5]
            ref = engine.storage.find_ref(source, source_id)
            if not ref:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "filing_not_found"})
            return self._json(
                HTTPStatus.OK,
                {
                    "filing": serialize_ref(ref),
                    "stored_path": engine.storage.get_path(ref),
                },
            )

        def _handle_runs(self, parsed):
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["20"])[0])
            runs = engine.state_store.list_runs(limit=limit)
            return self._json(
                HTTPStatus.OK,
                {
                    "items": [
                        {
                            "id": run.id,
                            "started_at": run.started_at,
                            "finished_at": run.finished_at,
                            "discovered": run.discovered,
                            "fetched": run.fetched,
                            "failed": run.failed,
                        }
                        for run in runs
                    ]
                },
            )

        def _handle_subscriptions_list(self, parsed):
            qs = parse_qs(parsed.query)
            active_only = qs.get("active_only", ["false"])[0].lower() == "true"
            subs = engine.state_store.list_subscriptions(
                source=qs.get("source", [None])[0],
                stock_code=qs.get("stock_code", [None])[0],
                active_only=active_only,
            )
            return self._json(
                HTTPStatus.OK,
                {"items": [serialize_subscription(sub) for sub in subs]},
            )

        def _handle_subscription_create(self):
            payload = self._read_json()
            if payload is None:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            name = (payload.get("name") or "").strip()
            if not name:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "name_required"})
            sub = Subscription(
                id=None,
                name=name,
                source=(payload.get("source") or "").strip(),
                stock_code=(payload.get("stock_code") or "").strip(),
                kind=(payload.get("kind") or "").strip(),
                target=(payload.get("target") or "").strip(),
                active=bool(payload.get("active", True)),
            )
            created = engine.state_store.create_subscription(sub)
            return self._json(
                HTTPStatus.CREATED,
                {"subscription": serialize_subscription(created)},
            )

        def _handle_sync(self):
            payload = self._read_json() or {}
            selected_sources = payload.get("sources") or None
            since = payload.get("since")
            if selected_sources is not None and not isinstance(selected_sources, list):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "sources_must_be_list"})
            if since is not None and not isinstance(since, str):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "since_must_be_string"})
            if not run_lock.acquire(blocking=False):
                return self._json(HTTPStatus.CONFLICT, {"error": "sync_already_running"})
            try:
                stats = engine.run_once(selected_sources=selected_sources, since=since)
            finally:
                run_lock.release()
            return self._json(HTTPStatus.OK, {"stats": stats})

        def _read_json(self) -> Dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return None

        def _json(self, status: HTTPStatus, payload: Dict[str, Any]):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((config.api.host, config.api.port), Handler)
    server.engine = engine  # type: ignore[attr-defined]
    return server


def serve(config: Config, source_registry: Dict[str, type]):
    server = create_app(config, source_registry)
    logger.info("HTTP API listening on %s:%d", config.api.host, config.api.port)
    try:
        server.serve_forever()
    finally:
        server.engine.close()  # type: ignore[attr-defined]
        server.server_close()


def serialize_ref(ref):
    return {
        "source": ref.source,
        "source_id": ref.source_id,
        "stock_code": ref.stock_code,
        "stock_name": ref.stock_name,
        "title": ref.title,
        "kind": ref.kind.value,
        "published_at": ref.published_at,
        "url": ref.url,
        "unique_key": ref.unique_key,
    }


def serialize_subscription(sub: Subscription):
    return {
        "id": sub.id,
        "name": sub.name,
        "source": sub.source,
        "stock_code": sub.stock_code,
        "kind": sub.kind,
        "target": sub.target,
        "active": sub.active,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
    }
