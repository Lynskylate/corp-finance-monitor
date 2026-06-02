from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from corp_finance_monitor.core import Config, Engine, FilingKind
from corp_finance_monitor.core.model import Subscription

logger = logging.getLogger("cfm.api")


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

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
        "file_size": ref.file_size,
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


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config: Config, source_registry: Dict[str, type]) -> FastAPI:
    """Build and return a FastAPI application with all API routes."""
    engine = Engine(config, source_registry)
    engine.initialize()

    app = FastAPI(title="corp-finance-monitor", version="0.1.0")

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- App-level state ---
    app.state.engine = engine
    app.state.run_lock = asyncio.Lock()
    app.state.executor = ThreadPoolExecutor(max_workers=4)

    # --- Helper: read JSON body safely ---

    async def _read_json_body(request: Request) -> Any:
        try:
            return await request.json()
        except Exception:
            return None

    # --- Routes ---

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/api/filings")
    async def list_filings(
        kind: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        since: Optional[str] = None,
        exchange: Optional[str] = None,
    ):
        if limit < 0 or offset < 0:
            raise HTTPException(status_code=400, detail="limit_offset_must_be_non_negative")
        filter_kind = FilingKind(kind) if kind else None
        refs = engine.storage.list_refs(
            source=source,
            stock_code=stock_code,
            kind=filter_kind,
            since=since,
            limit=limit or None,
            offset=offset,
            exchange=exchange,
        )
        total = engine.storage.count_refs(
            source=source,
            stock_code=stock_code,
            kind=filter_kind,
            since=since,
            exchange=exchange,
        )
        return {
            "items": [serialize_ref(ref) for ref in refs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/filings/{source}/{source_id}")
    async def filing_detail(source: str, source_id: str):
        ref = engine.storage.find_ref(source, source_id)
        if not ref:
            raise HTTPException(status_code=404, detail="filing_not_found")
        return {
            "filing": serialize_ref(ref),
            "stored_path": engine.storage.get_path(ref),
        }

    @app.get("/api/runs")
    async def list_runs(limit: int = 20):
        runs = engine.state_store.list_runs(limit=limit)
        return {
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
        }

    @app.get("/api/subscriptions")
    async def list_subscriptions(
        active_only: bool = False,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
    ):
        subs = engine.state_store.list_subscriptions(
            source=source,
            stock_code=stock_code,
            active_only=active_only,
        )
        return {"items": [serialize_subscription(sub) for sub in subs]}

    @app.post("/api/subscriptions", status_code=201)
    async def create_subscription(request: Request):
        payload = await _read_json_body(request)
        if payload is None:
            raise HTTPException(status_code=400, detail="invalid_json")
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name_required")
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
        return {"subscription": serialize_subscription(created)}

    @app.post("/api/sync")
    async def sync(request: Request):
        payload = await _read_json_body(request)
        if payload is None:
            payload = {}
        selected_sources = payload.get("sources") or None
        since = payload.get("since")
        resume = payload.get("resume", True)
        if selected_sources is not None and not isinstance(selected_sources, list):
            raise HTTPException(status_code=400, detail="sources_must_be_list")
        if since is not None and not isinstance(since, str):
            raise HTTPException(status_code=400, detail="since_must_be_string")
        if not isinstance(resume, bool):
            raise HTTPException(status_code=400, detail="resume_must_be_boolean")
        if app.state.run_lock.locked():
            raise HTTPException(status_code=409, detail="sync_already_running")
        async with app.state.run_lock:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(
                app.state.executor,
                lambda: engine.run_once(selected_sources=selected_sources, since=since, resume=resume),
            )
        return {"stats": stats}

    @app.get("/api/filings/{source}/{source_id}/file")
    async def filing_file(source: str, source_id: str):
        ref = engine.storage.find_ref(source, source_id)
        if not ref:
            raise HTTPException(status_code=404, detail="filing_not_found")
        stored_path = engine.storage.get_path(ref)
        if not stored_path or not os.path.exists(stored_path):
            raise HTTPException(status_code=404, detail="file_not_found")
        return FileResponse(
            stored_path,
            media_type="application/pdf",
            filename=os.path.basename(stored_path),
        )

    @app.get("/api/stats")
    async def stats():
        total = engine.storage.count_refs()
        by_source: Dict[str, int] = {}
        for src in engine.storage.list_distinct_sources():
            by_source[src] = engine.storage.count_refs(source=src)
        by_kind: Dict[str, int] = {}
        for kind in engine.storage.list_distinct_kinds():
            by_kind[kind] = engine.storage.count_refs(kind=FilingKind(kind))
        return {"total": total, "by_source": by_source, "by_kind": by_kind}

    @app.delete("/api/subscriptions/{subscription_id}")
    async def delete_subscription(subscription_id: int):
        deleted = engine.state_store.delete_subscription(subscription_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="subscription_not_found")
        return {"ok": True}

    @app.post("/api/backfill")
    async def backfill():
        if app.state.run_lock.locked():
            raise HTTPException(status_code=409, detail="sync_already_running")
        async with app.state.run_lock:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(
                app.state.executor,
                lambda: engine.backfill(),
            )
        return {"stats": stats}

    return app


def serve(config: Config, source_registry: Dict[str, type]):
    import uvicorn

    app = create_app(config, source_registry)
    logger.info("FastAPI API listening on %s:%d", config.api.host, config.api.port)
    try:
        uvicorn.run(app, host=config.api.host, port=config.api.port, log_level="info")
    finally:
        engine = app.state.engine
        engine.close()
