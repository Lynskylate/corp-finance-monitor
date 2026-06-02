from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from .config import Config, SchedulingTierConfig
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
        tier: Optional[str] = None,
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
        tier_cfg = self._get_tier_config(tier)

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
                resume=resume,
                tier=tier_cfg,
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
        resume: bool,
        tier: Optional[SchedulingTierConfig],
    ) -> Dict[str, int]:
        refs = self._discover_refs(
            name=name,
            source=source,
            since=since,
            concurrency=concurrency,
            resume=resume,
            tier=tier,
        )
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
        resume: bool,
        tier: Optional[SchedulingTierConfig],
    ) -> List[FilingRef]:
        scfg = self.config.sources[name]
        logger.info("Source [%s]: discovering...", name)

        tier_stock_codes = self._resolve_tier_stock_codes(name, source, tier)
        watchlist = self._resolve_source_watchlist(name, source, tier_stock_codes)
        use_full_market_progress = False
        use_batched_discover = self._should_use_batched_discover(
            source=source,
            scfg=scfg,
            concurrency=concurrency,
            tier=tier,
            tier_stock_codes=tier_stock_codes,
        )

        if (
            (tier is None or tier.use_registry)
            and source.name == "cninfo"
            and bool(scfg.options.get("full_market", False))
        ):
            use_full_market_progress = True

        if use_full_market_progress and not resume and self.state_store:
            self.state_store.clear_scan_progress(name)

        if source.name == "cninfo" and tier_stock_codes == []:
            logger.info("Source [%s]: no matching stocks for tier, skipping", name)
            return []

        if not use_batched_discover:
            try:
                return source.discover(
                    watchlist,
                    since=since,
                )
            except Exception as exc:
                logger.error("Source [%s] discover failed: %s", name, exc)
                return []

        stock_codes = tier_stock_codes if tier_stock_codes is not None else self._get_full_market_stock_codes(source)
        if not stock_codes:
            return []

        # Skip already-scanned stocks when resuming a full-market pass.
        if use_full_market_progress and resume and self.state_store:
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
        scanned_count = 0

        logger.info(
            "Source [%s]: batched discover in %d batch(es), batch_size=%d, workers=%d",
            name,
            total_batches,
            batch_size,
            workers,
        )

        completed_batches = 0
        if workers <= 1:
            for batch in batches:
                try:
                    batch_refs = source.discover(watchlist, since, batch)
                    refs.extend(batch_refs)
                    scanned_count += len(batch)
                    if use_full_market_progress and self.state_store:
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
                logger.info(
                    "Source [%s]: batch %d/%d done, %d/%d stocks scanned",
                    name,
                    completed_batches,
                    total_batches,
                    scanned_count,
                    len(stock_codes),
                )
            return refs

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(
                    source.discover,
                    watchlist,
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
                    scanned_count += len(batch)
                    if use_full_market_progress and self.state_store:
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
                logger.info(
                    "Source [%s]: batch %d/%d done, %d/%d stocks scanned",
                    name,
                    completed_batches,
                    total_batches,
                    scanned_count,
                    len(stock_codes),
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
    def _should_use_batched_discover(
        source: AbstractSource,
        scfg,
        concurrency: int,
        tier: Optional[SchedulingTierConfig],
        tier_stock_codes: Optional[Sequence[str]],
    ) -> bool:
        if source.name != "cninfo":
            return False
        if bool(scfg.options.get("full_market", False)) and (tier is None or tier.use_registry):
            return True
        return concurrency > 1 and tier_stock_codes is not None

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

    def run_loop(self, tier: Optional[str] = None):
        """持续运行: 定期轮询."""
        tier_cfg = self._get_tier_config(tier)

        if tier_cfg is not None:
            interval = self._tier_interval_seconds(tier_cfg)
            logger.info(
                "Engine started for tier [%s]. Interval: %.2f minutes",
                tier_cfg.name,
                interval / 60,
            )
            while True:
                stats = self.run_once(tier=tier_cfg.name)
                logger.info("Tier [%s] round complete: %s", tier_cfg.name, stats)
                logger.info("Next tier [%s] check in %.2f minutes...", tier_cfg.name, interval / 60)
                time.sleep(interval)
            return

        if not self.config.scheduling.tiers:
            interval = self.config.engine.interval_minutes * 60
            logger.info("Engine started. Interval: %d minutes", self.config.engine.interval_minutes)
            while True:
                stats = self.run_once()
                logger.info("Round complete: %s", stats)
                logger.info("Next check in %d minutes...", self.config.engine.interval_minutes)
                time.sleep(interval)
            return

        next_due = {tier_item.name: time.monotonic() for tier_item in self.config.scheduling.tiers}
        logger.info(
            "Engine started with scheduling tiers: %s",
            ", ".join(tier_item.name for tier_item in self.config.scheduling.tiers),
        )
        while True:
            now = time.monotonic()
            due_tiers = [
                tier_item
                for tier_item in self.config.scheduling.tiers
                if now >= next_due[tier_item.name]
            ]
            if not due_tiers:
                sleep_for = min(next_due.values()) - now
                time.sleep(max(0.1, sleep_for))
                continue

            for tier_item in due_tiers:
                stats = self.run_once(tier=tier_item.name)
                logger.info("Tier [%s] round complete: %s", tier_item.name, stats)
                next_due[tier_item.name] = time.monotonic() + self._tier_interval_seconds(tier_item)

    def backfill(self) -> Dict[str, int]:
        """
        一次性回填历史数据：
        对 file_size=0 的记录，从磁盘读取本地文件大小并更新。

        URL 在首次 discover 时已持久化到 meta.db；如有缺失，
        下一轮正常 sync 会自然补全（discover 返回的 ref 带 url）。
        不再通过远程 API 全量 re-discover 来补 url，避免长时间阻塞。

        返回统计: {file_size_updated}
        """
        stats = {"file_size_updated": 0}

        if not (self.storage and hasattr(self.storage, "_meta_db") and self.storage._meta_db):
            logger.warning("Backfill: no meta_db available on storage, skipping")
            return stats

        logger.info("Backfill: updating file_size from local disk...")
        with self.storage._lock:
            rows = self.storage._meta_db.execute(
                "SELECT unique_key, stored_path FROM filings WHERE file_size = 0 OR file_size IS NULL"
            ).fetchall()

        for row in rows:
            stored_path = row["stored_path"]
            if stored_path and os.path.exists(stored_path):
                size = os.path.getsize(stored_path)
                if size > 0:
                    with self.storage._lock:
                        self.storage._meta_db.execute(
                            "UPDATE filings SET file_size = ? WHERE unique_key = ?",
                            (size, row["unique_key"]),
                        )
                    self.storage._meta_db.commit()
                    stats["file_size_updated"] += 1

        logger.info("Backfill: updated file_size for %d record(s)", stats["file_size_updated"])
        return stats

    def close(self):
        for source in self.sources.values():
            source.close()
        if self.state_store:
            self.state_store.close()
        if self.storage and hasattr(self.storage, "close"):
            self.storage.close()

    def _get_tier_config(self, tier: Optional[str]) -> Optional[SchedulingTierConfig]:
        if tier is None:
            return None
        for item in self.config.scheduling.tiers:
            if item.name == tier:
                return item
        raise ValueError(f"Unknown scheduling tier: {tier}")

    def _tier_interval_seconds(
        self,
        tier: SchedulingTierConfig,
        month: Optional[int] = None,
    ) -> float:
        month = month or datetime.utcnow().month
        multiplier = 1.0
        matched = [
            window.multiplier
            for window in self.config.scheduling.disclosure_windows
            if month in window.months
        ]
        if matched:
            multiplier = min(matched)
        return tier.interval_minutes * 60 * multiplier

    def _resolve_tier_stock_codes(
        self,
        name: str,
        source: AbstractSource,
        tier: Optional[SchedulingTierConfig],
    ) -> Optional[List[str]]:
        if tier is None or not tier.stocks:
            return None
        if source.name == "cninfo":
            return list(tier.stocks)
        matched = [
            entry.get("stock", "")
            for entry in self.config.sources[name].watchlist
            if entry.get("stock", "") in set(tier.stocks)
        ]
        return matched

    def _resolve_source_watchlist(
        self,
        name: str,
        source: AbstractSource,
        tier_stock_codes: Optional[Sequence[str]],
    ) -> Optional[List[dict]]:
        scfg = self.config.sources[name]
        if tier_stock_codes is None:
            return scfg.watchlist

        if source.name != "cninfo":
            return [
                entry
                for entry in scfg.watchlist
                if entry.get("stock", "") in set(tier_stock_codes)
            ]

        kinds = source.options.get("kinds", ["annual", "semi", "q1", "q3"])
        by_stock = {
            entry.get("stock", ""): dict(entry)
            for entry in scfg.watchlist
            if entry.get("stock")
        }
        watchlist: List[dict] = []
        missing_codes: List[str] = []
        for code in tier_stock_codes:
            if code in by_stock:
                watchlist.append(by_stock[code])
                continue
            missing_codes.append(code)

        if missing_codes and hasattr(source, "_get_registry"):
            try:
                registry = source._get_registry()  # type: ignore[attr-defined]
                for code in missing_codes:
                    entry = registry.lookup(code)
                    if entry is None:
                        logger.warning("Source [%s]: stock %s not found in registry", name, code)
                        continue
                    watchlist.append(entry.to_watchlist_entry(kinds=kinds))
            except Exception as exc:
                logger.error("Source [%s]: failed to resolve tier stocks from registry: %s", name, exc)

        return watchlist
