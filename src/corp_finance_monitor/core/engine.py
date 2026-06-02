from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from .config import Config
from .model import FilingRef
from .source import AbstractSource
from .storage import AbstractStorage
from .state import AbstractStateStore

logger = logging.getLogger("cfm")


class RateLimiter:
    """Simple shared rate limiter preserving fetch_delay_seconds semantics."""

    def __init__(self, min_interval_seconds: float):
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self):
        if self._min_interval <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_allowed:
                    self._next_allowed = now + self._min_interval
                    return
                sleep_for = self._next_allowed - now
            if sleep_for > 0:
                time.sleep(sleep_for)


class Engine:
    """
    财报发现引擎

    编排: Config → Sources → discover → fetch → Storage
    支持: 去重、状态追踪(断点续跑)、定期轮询
    """

    def __init__(self, config: Config, source_registry: Dict[str, type]):
        self.config = config
        self.sources: Dict[str, AbstractSource] = {}
        self.storage: Optional[AbstractStorage] = None
        self.state_store: Optional[AbstractStateStore] = None
        self.notifier_registry: Optional[NotifierRegistry] = None
        self._source_registry = source_registry

    def initialize(self):
        """初始化: 创建存储、加载source、打开状态数据库、初始化通知器"""
        self._init_storage()
        self._init_state_store()
        self._init_sources()
        self._init_notifiers()

    def _init_storage(self):
        storage_cls = self._get_storage_class()
        self.storage = storage_cls(self.config.storage)
        self.storage.initialize()

    def _init_state_store(self):
        state_store_cls = self._get_state_store_class()
        self.state_store = state_store_cls(self.config.state_store)
        self.state_store.initialize()

    def _get_storage_class(self):
        backend = self.config.storage.backend
        if backend == "disk":
            from corp_finance_monitor.storage.disk import DiskStorage
            return DiskStorage
        raise ValueError(f"Unknown storage backend: {backend}")

    def _get_state_store_class(self):
        backend = self.config.state_store.backend
        if backend == "sqlite":
            from corp_finance_monitor.state.sqlite import SQLiteStateStore
            return SQLiteStateStore
        raise ValueError(f"Unknown state store backend: {backend}")

    def _init_sources(self):
        for name, scfg in self.config.sources.items():
            if not scfg.enabled:
                continue
            cls = self._source_registry.get(name)
            if cls is None:
                logger.warning("No source class registered for '%s', skipping", name)
                continue
            self.sources[name] = cls(name, scfg)

    def _init_notifiers(self):
        """Initialize the notifier registry with built-in notifiers."""
        from corp_finance_monitor.notifiers.registry import NotifierRegistry
        from corp_finance_monitor.notifiers.webhook import WebhookNotifier
        from corp_finance_monitor.notifiers.email import EmailNotifier
        from corp_finance_monitor.notifiers.wechat import WeChatNotifier

        self.notifier_registry = NotifierRegistry()
        self.notifier_registry.register(WebhookNotifier())
        self.notifier_registry.register(EmailNotifier())
        self.notifier_registry.register(WeChatNotifier())

    def run_once(
        self,
        selected_sources: Optional[Sequence[str]] = None,
        since: Optional[str] = None,
        resume: bool = False,
    ) -> Dict[str, int]:
        """
        执行一轮发现-下载流程。

        selected_sources: 仅运行指定的数据源。
        since: 仅发现此日期之后发布的文件 (YYYY-MM-DD)。
               若为 None，则自动使用上次成功运行的时间。
               若从未运行过，则发现所有文件。
        resume: 若为 True，从上次断点继续扫描（跳过已完成股票）。
                若为 False，清空进度重新开始。
        返回统计数据: {discovered, fetched, failed}
        """
        if not resume and self.state_store:
            self.state_store.clear_scan_progress()

        run_start = datetime.utcnow().isoformat()
        stats = {"discovered": 0, "fetched": 0, "failed": 0}
        selected = set(selected_sources or [])

        # Resolve since date:
        #   explicit YYYY-MM-DD → use as-is
        #   "full" or empty     → full sync, no date filter
        #   None                → auto from last successful run
        effective_since = since
        if effective_since == "full":
            effective_since = None
        elif effective_since is None and self.state_store:
            effective_since = self.state_store.last_successful_run_start()
            # Truncate ISO timestamp to date-only (YYYY-MM-DD) for API compatibility
            if effective_since and len(effective_since) > 10:
                effective_since = effective_since[:10]

        if since == "full":
            logger.info("Full sync (forced, no date filter)")
        elif effective_since:
            logger.info("Incremental sync since: %s", effective_since)
        else:
            logger.info("Full sync (no previous successful run)")

        concurrency = max(1, int(self.config.engine.concurrency or 1))
        rate_limiter = RateLimiter(self.config.engine.fetch_delay_seconds)

        for name, source in self.sources.items():
            if selected and name not in selected:
                continue
            source_stats = self._run_source_once(
                name=name,
                source=source,
                since=effective_since,
                concurrency=concurrency,
                rate_limiter=rate_limiter,
            )
            stats["discovered"] += source_stats["discovered"]
            stats["fetched"] += source_stats["fetched"]
            stats["failed"] += source_stats["failed"]

        run_end = datetime.utcnow().isoformat()
        self.state_store.record_run(
            run_start,
            run_end,
            stats["discovered"],
            stats["fetched"],
            stats["failed"],
        )
        return stats

    def _run_source_once(
        self,
        name: str,
        source: AbstractSource,
        since: Optional[str],
        concurrency: int,
        rate_limiter: RateLimiter,
    ) -> Dict[str, int]:
        refs = self._discover_refs(name=name, source=source, since=since, concurrency=concurrency)
        logger.info("Source [%s]: discovered %d filing(s)", name, len(refs))
        if concurrency <= 1:
            return self._fetch_refs_serial(source, refs)
        return self._fetch_refs_parallel(source, refs, concurrency, rate_limiter)

    def _discover_refs(
        self,
        name: str,
        source: AbstractSource,
        since: Optional[str],
        concurrency: int,
    ) -> List[FilingRef]:
        scfg = self.config.sources[name]
        logger.info("Source [%s]: discovering...", name)

        if not self._supports_full_market_batching(source, scfg, concurrency):
            try:
                return source.discover(scfg.watchlist, since=since)
            except Exception as exc:
                logger.error("Source [%s] discover failed: %s", name, exc)
                return []

        stock_codes = self._get_full_market_stock_codes(source)
        if not stock_codes:
            return []

        # Skip already-scanned stocks when resuming
        if self.state_store:
            before = len(stock_codes)
            stock_codes = [
                code for code in stock_codes
                if not self.state_store.is_scan_done(name, code)
            ]
            skipped = before - len(stock_codes)
            if skipped:
                logger.info(
                    "Source [%s]: resuming — skipped %d already-scanned stocks, %d remaining",
                    name, skipped, len(stock_codes),
                )

        if not stock_codes:
            return []

        batch_size = max(1, int(scfg.options.get("full_market_batch_size", 50) or 50))
        refs: List[FilingRef] = []
        batches = list(self._chunked(stock_codes, batch_size))
        workers = min(concurrency, len(batches))
        total_batches = len(batches)

        logger.info(
            "Source [%s]: full_market discover in %d batch(es), batch_size=%d, workers=%d",
            name,
            total_batches,
            batch_size,
            workers,
        )

        completed_batches = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(
                    source.discover,
                    scfg.watchlist,
                    since,
                    batch,
                ): batch
                for batch in batches
            }
            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    batch_refs = future.result()
                    refs.extend(batch_refs)
                    # Mark each stock in this batch as scanned
                    if self.state_store:
                        for code in batch:
                            self.state_store.mark_scan_done(name, code)
                except Exception as exc:
                    logger.error(
                        "Source [%s] discover batch failed (%s..%s): %s",
                        name,
                        batch[0],
                        batch[-1],
                        exc,
                    )
                completed_batches += 1
                done_count, _ = (
                    self.state_store.count_scan_progress(name)
                    if self.state_store else (completed_batches * batch_size, 0)
                )
                logger.info(
                    "Source [%s]: batch %d/%d done, %d stocks scanned",
                    name, completed_batches, total_batches, done_count,
                )
        return refs

    def _fetch_refs_serial(
        self,
        source: AbstractSource,
        refs: Sequence[FilingRef],
    ) -> Dict[str, int]:
        stats = {"discovered": len(refs), "fetched": 0, "failed": 0}
        for ref in refs:
            if self._is_already_fetched(ref):
                logger.debug("  SKIP (already fetched): %s", ref.title)
                continue

            logger.info("  FETCH: [%s] %s - %s", ref.stock_code, ref.title, ref.url or "")
            try:
                filing = source.fetch(ref)
                if filing is None:
                    logger.warning("  FAILED: fetch returned None for %s", ref.title)
                    stats["failed"] += 1
                    continue

                stored_path = self.storage.store(filing)
                self._record_state(ref, stored_path)
                self._notify(ref, stored_path)
                stats["fetched"] += 1
            except Exception as exc:
                logger.error("  FAILED: %s - %s", ref.title, exc)
                stats["failed"] += 1

            time.sleep(self.config.engine.fetch_delay_seconds)
        return stats

    def _fetch_refs_parallel(
        self,
        source: AbstractSource,
        refs: Sequence[FilingRef],
        concurrency: int,
        rate_limiter: RateLimiter,
    ) -> Dict[str, int]:
        stats = {"discovered": len(refs), "fetched": 0, "failed": 0}
        if not refs:
            return stats

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures: List[Future] = [
                pool.submit(self._fetch_ref, source, ref, rate_limiter)
                for ref in refs
            ]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    logger.error("Unhandled fetch worker failure: %s", exc)
                    stats["failed"] += 1
                    continue
                stats["fetched"] += result["fetched"]
                stats["failed"] += result["failed"]
        return stats

    def _fetch_ref(
        self,
        source: AbstractSource,
        ref: FilingRef,
        rate_limiter: RateLimiter,
    ) -> Dict[str, int]:
        if self._is_already_fetched(ref):
            logger.debug("  SKIP (already fetched): %s", ref.title)
            return {"fetched": 0, "failed": 0}

        logger.info("  FETCH: [%s] %s - %s", ref.stock_code, ref.title, ref.url or "")
        try:
            rate_limiter.wait()
            filing = source.fetch(ref)
            if filing is None:
                logger.warning("  FAILED: fetch returned None for %s", ref.title)
                return {"fetched": 0, "failed": 1}

            stored_path = self.storage.store(filing)
            self._record_state(ref, stored_path)
            self._notify(ref, stored_path)
            return {"fetched": 1, "failed": 0}
        except Exception as exc:
            logger.error("  FAILED: %s - %s", ref.title, exc)
            return {"fetched": 0, "failed": 1}

    @staticmethod
    def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
        for idx in range(0, len(items), size):
            yield list(items[idx:idx + size])

    @staticmethod
    def _supports_full_market_batching(
        source: AbstractSource,
        scfg,
        concurrency: int,
    ) -> bool:
        return (
            concurrency > 1
            and source.name == "cninfo"
            and bool(scfg.options.get("full_market", False))
        )

    @staticmethod
    def _get_full_market_stock_codes(source: AbstractSource) -> List[str]:
        if not hasattr(source, "_get_registry"):
            return []
        try:
            registry = source._get_registry()  # type: ignore[attr-defined]
            stocks = registry.get_a_shares()
        except Exception as exc:
            logger.error("Failed to load full-market stock registry: %s", exc)
            return []

        limit = int(source.options.get("full_market_limit", 0) or 0)
        stock_codes = [entry.stock_code for entry in stocks]
        if limit:
            stock_codes = stock_codes[:limit]
        return stock_codes

    def _is_already_fetched(self, ref: FilingRef) -> bool:
        if self.state_store and self.state_store.has_filing(ref):
            return True
        if self.storage and self.storage.exists(ref):
            stored_path = self.storage.get_path(ref) or ""
            self.storage.upsert_metadata(ref, stored_path=stored_path)
            self._record_state(ref, stored_path)
            return True
        return False

    def _record_state(self, ref: FilingRef, stored_path: str):
        if self.state_store:
            self.state_store.record_filing(ref, stored_path)

    def _notify(self, ref: FilingRef, stored_path: str):
        """Load active subscriptions and dispatch notifications."""
        if not self.notifier_registry or not self.state_store:
            return
        try:
            subs = self.state_store.list_subscriptions(active_only=True)
            if not subs:
                return
            results = self.notifier_registry.dispatch(subs, ref, stored_path)
            for r in results:
                if r.success:
                    logger.debug(
                        "  NOTIFY %s OK → %s", r.channel, r.target
                    )
                else:
                    logger.warning(
                        "  NOTIFY %s FAILED → %s: %s",
                        r.channel,
                        r.target,
                        r.message,
                    )
        except Exception as e:
            logger.error("Notification dispatch error: %s", e)

    def run_loop(self):
        """持续运行: 定期轮询"""
        interval = self.config.engine.interval_minutes * 60
        logger.info("Engine started. Interval: %d minutes", self.config.engine.interval_minutes)
        while True:
            stats = self.run_once()
            logger.info("Round complete: %s", stats)
            logger.info("Next check in %d minutes...", self.config.engine.interval_minutes)
            time.sleep(interval)

    def close(self):
        for source in self.sources.values():
            source.close()
        if self.state_store:
            self.state_store.close()
        if self.storage and hasattr(self.storage, "close"):
            self.storage.close()
