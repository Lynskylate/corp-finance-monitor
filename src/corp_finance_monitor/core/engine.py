from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime

from corp_finance_monitor.notifiers.registry import NotifierRegistry

from .config import Config, SchedulingTierConfig
from .model import FilingRef
from .source import AbstractSource
from .state import AbstractStateStore
from .storage import AbstractStorage

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

    def __init__(self, config: Config, source_registry: dict[str, type]):
        self.config = config
        self.sources: dict[str, AbstractSource] = {}
        self.storage: AbstractStorage | None = None
        self.state_store: AbstractStateStore | None = None
        self.notifier_registry: NotifierRegistry | None = None
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
        from corp_finance_monitor.notifiers.email import EmailNotifier
        from corp_finance_monitor.notifiers.registry import NotifierRegistry
        from corp_finance_monitor.notifiers.webhook import WebhookNotifier
        from corp_finance_monitor.notifiers.wechat import WeChatNotifier

        self.notifier_registry = NotifierRegistry()
        self.notifier_registry.register(WebhookNotifier())
        self.notifier_registry.register(EmailNotifier())
        self.notifier_registry.register(WeChatNotifier())

    def run_once(
        self,
        selected_sources: Sequence[str] | None = None,
        since: str | None = None,
        resume: bool = True,
        tier: str | None = None,
    ) -> dict[str, int]:
        """
        执行一轮发现-下载流程。

        selected_sources: 仅运行指定的数据源。
        since: 仅发现此日期之后发布的文件 (YYYY-MM-DD)。
               若为 None，则自动使用上次成功运行的时间。
               若从未运行过，则发现所有文件。
        resume: 若为 True，从上次断点继续扫描（跳过已完成股票）。
                 若为 False，扫描所有股票但不清空进度。
                 要清空进度请使用 state_store.clear_scan_progress() 显式调用。
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
        since: str | None,
        concurrency: int,
        rate_limiter: RateLimiter,
        resume: bool,
        tier: SchedulingTierConfig | None,
    ) -> dict[str, int]:
        refs_or_stats = self._discover_refs(
            name=name,
            source=source,
            since=since,
            concurrency=concurrency,
            resume=resume,
            tier=tier,
            rate_limiter=rate_limiter,
        )
        if isinstance(refs_or_stats, dict):
            return refs_or_stats
        refs = refs_or_stats
        logger.info("Source [%s]: discovered %d filing(s)", name, len(refs))
        if concurrency <= 1:
            return self._fetch_refs_serial(source, refs)
        return self._fetch_refs_parallel(source, refs, concurrency, rate_limiter)

    def _discover_refs(
        self,
        name: str,
        source: AbstractSource,
        since: str | None,
        concurrency: int,
        resume: bool,
        tier: SchedulingTierConfig | None,
        rate_limiter: RateLimiter,
    ) -> list[FilingRef] | dict[str, int]:
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
            and hasattr(source, "_get_registry")
            and bool(scfg.options.get("full_market", False))
        ):
            use_full_market_progress = True

        if hasattr(source, "_get_registry") and tier_stock_codes == []:
            logger.info("Source [%s]: no matching stocks for tier, skipping", name)
            return []

        if not use_batched_discover:
            try:
                refs = source.discover(
                    watchlist,
                    since=since,
                )
                self._log_discovered_refs(name, refs)
                return refs
            except Exception as exc:
                logger.error("Source [%s] discover failed: %s", name, exc)
                return []

        stock_codes = (
            tier_stock_codes
            if tier_stock_codes is not None
            else self._get_full_market_stock_codes(source)
        )
        if not stock_codes:
            return []

        # Skip already-scanned stocks — default incremental behavior.
        if use_full_market_progress and self.state_store:
            before = len(stock_codes)
            stock_codes = [
                code for code in stock_codes if not self.state_store.is_scan_done(name, code)
            ]
            skipped = before - len(stock_codes)
            if skipped:
                logger.info(
                    "Source [%s]: resuming — skipped %d already-scanned stocks, %d remaining",
                    name,
                    skipped,
                    len(stock_codes),
                )

        if not stock_codes:
            return []

        batch_size = max(1, int(scfg.options.get("full_market_batch_size", 50) or 50))
        refs: list[FilingRef] = []
        batches = list(self._chunked(stock_codes, batch_size))
        workers = min(concurrency, len(batches))
        total_batches = len(batches)
        scanned_count = 0
        streamed_stats = {"discovered": 0, "fetched": 0, "failed": 0}
        stream_fetch = workers <= 1

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
                    if stream_fetch:
                        batch_stats = self._fetch_refs_serial(source, batch_refs)
                        streamed_stats["discovered"] += batch_stats["discovered"]
                        streamed_stats["fetched"] += batch_stats["fetched"]
                        streamed_stats["failed"] += batch_stats["failed"]
                    else:
                        refs.extend(batch_refs)
                    self._log_discovered_refs(name, batch_refs)
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
                    recovered_refs, recovered_stats, recovered_count = self._recover_failed_batch(
                        name=name,
                        source=source,
                        watchlist=watchlist,
                        since=since,
                        batch=batch,
                        use_full_market_progress=use_full_market_progress,
                        stream_fetch=stream_fetch,
                    )
                    if stream_fetch:
                        streamed_stats["discovered"] += recovered_stats["discovered"]
                        streamed_stats["fetched"] += recovered_stats["fetched"]
                        streamed_stats["failed"] += recovered_stats["failed"]
                    else:
                        refs.extend(recovered_refs)
                    scanned_count += recovered_count
                completed_batches += 1
                logger.info(
                    "Source [%s]: batch %d/%d done, %d/%d stocks scanned",
                    name,
                    completed_batches,
                    total_batches,
                    scanned_count,
                    len(stock_codes),
                )
            if stream_fetch:
                return streamed_stats
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
                    self._log_discovered_refs(name, batch_refs)
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
                    recovered_refs, _, recovered_count = self._recover_failed_batch(
                        name=name,
                        source=source,
                        watchlist=watchlist,
                        since=since,
                        batch=batch,
                        use_full_market_progress=use_full_market_progress,
                        stream_fetch=False,
                    )
                    refs.extend(recovered_refs)
                    scanned_count += recovered_count
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

    def _recover_failed_batch(
        self,
        name: str,
        source: AbstractSource,
        watchlist: list[dict],
        since: str | None,
        batch: Sequence[str],
        use_full_market_progress: bool,
        stream_fetch: bool,
    ) -> tuple[list[FilingRef], dict[str, int], int]:
        if len(batch) <= 1:
            return [], {"discovered": 0, "fetched": 0, "failed": 0}, 0

        logger.info(
            "Source [%s]: retrying failed batch per stock (%s..%s, %d stock(s))",
            name,
            batch[0],
            batch[-1],
            len(batch),
        )

        recovered_refs: list[FilingRef] = []
        recovered_stats = {"discovered": 0, "fetched": 0, "failed": 0}
        recovered_count = 0

        for code in batch:
            try:
                code_refs = source.discover(watchlist, since, [code])
                self._log_discovered_refs(name, code_refs)
                if stream_fetch:
                    code_stats = self._fetch_refs_serial(source, code_refs)
                    recovered_stats["discovered"] += code_stats["discovered"]
                    recovered_stats["fetched"] += code_stats["fetched"]
                    recovered_stats["failed"] += code_stats["failed"]
                else:
                    recovered_refs.extend(code_refs)
                if use_full_market_progress and self.state_store:
                    self.state_store.mark_scan_done(name, code)
                recovered_count += 1
            except Exception as exc:
                logger.error(
                    "Source [%s] discover fallback failed (%s): %s",
                    name,
                    code,
                    exc,
                )

        return recovered_refs, recovered_stats, recovered_count

    def _fetch_refs_serial(
        self,
        source: AbstractSource,
        refs: Sequence[FilingRef],
    ) -> dict[str, int]:
        stats = {"discovered": len(refs), "fetched": 0, "failed": 0}
        for ref in refs:
            if self._is_already_fetched(ref):
                self._log_filing_result("skip", ref, reason="already_fetched")
                continue

            try:
                filing = source.fetch(ref)
                if filing is None:
                    self._log_filing_result("fetch_fail", ref, reason="fetch_returned_none")
                    stats["failed"] += 1
                    continue

                stored_path = self.storage.store(filing)
                self._record_state(ref, stored_path)
                self._notify(ref, stored_path)
                self._log_filing_result("fetch_ok", ref, stored_path=stored_path)
                stats["fetched"] += 1
            except Exception as exc:
                self._log_filing_result("fetch_fail", ref, reason=str(exc))
                stats["failed"] += 1

            time.sleep(self.config.engine.fetch_delay_seconds)
        return stats

    def _fetch_refs_parallel(
        self,
        source: AbstractSource,
        refs: Sequence[FilingRef],
        concurrency: int,
        rate_limiter: RateLimiter,
    ) -> dict[str, int]:
        stats = {"discovered": len(refs), "fetched": 0, "failed": 0}
        if not refs:
            return stats

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures: list[Future] = [
                pool.submit(self._fetch_ref, source, ref, rate_limiter) for ref in refs
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
    ) -> dict[str, int]:
        if self._is_already_fetched(ref):
            self._log_filing_result("skip", ref, reason="already_fetched")
            return {"fetched": 0, "failed": 0}

        try:
            rate_limiter.wait()
            filing = source.fetch(ref)
            if filing is None:
                self._log_filing_result("fetch_fail", ref, reason="fetch_returned_none")
                return {"fetched": 0, "failed": 1}

            stored_path = self.storage.store(filing)
            self._record_state(ref, stored_path)
            self._notify(ref, stored_path)
            self._log_filing_result("fetch_ok", ref, stored_path=stored_path)
            return {"fetched": 1, "failed": 0}
        except Exception as exc:
            self._log_filing_result("fetch_fail", ref, reason=str(exc))
            return {"fetched": 0, "failed": 1}

    def _log_discovered_refs(self, source_name: str, refs: Sequence[FilingRef]) -> None:
        for ref in refs:
            logger.info(
                "filing_event stage=discover result=found source=%s source_id=%s stock_code=%s title=%r published_at=%s url=%s",
                source_name,
                ref.source_id,
                ref.stock_code,
                ref.title,
                ref.published_at or "",
                ref.url or "",
            )

    def _log_filing_result(
        self,
        result: str,
        ref: FilingRef,
        reason: str = "",
        stored_path: str = "",
    ) -> None:
        logger.info(
            "filing_event stage=fetch result=%s source=%s source_id=%s stock_code=%s title=%r reason=%s stored_path=%s url=%s",
            result,
            ref.source,
            ref.source_id,
            ref.stock_code,
            ref.title,
            reason,
            stored_path,
            ref.url or "",
        )

    @staticmethod
    def _chunked(items: Sequence[str], size: int) -> Iterable[list[str]]:
        for idx in range(0, len(items), size):
            yield list(items[idx : idx + size])

    @staticmethod
    def _supports_full_market_batching(
        source: AbstractSource,
        scfg,
        concurrency: int,
    ) -> bool:
        return (
            concurrency > 1
            and hasattr(source, "_get_registry")
            and bool(scfg.options.get("full_market", False))
        )

    @staticmethod
    def _should_use_batched_discover(
        source: AbstractSource,
        scfg,
        concurrency: int,
        tier: SchedulingTierConfig | None,
        tier_stock_codes: Sequence[str] | None,
    ) -> bool:
        if not hasattr(source, "_get_registry"):
            return False
        if bool(scfg.options.get("full_market", False)):
            return True
        return concurrency > 1 and tier_stock_codes is not None

    @staticmethod
    def _get_full_market_stock_codes(source: AbstractSource) -> list[str]:
        if not hasattr(source, "_get_registry"):
            return []
        try:
            registry = source._get_registry()  # type: ignore[attr-defined]
            if hasattr(registry, "get_stock_codes"):
                stock_codes = registry.get_stock_codes()
            else:
                stock_codes = [entry.stock_code for entry in registry.get_a_shares()]
        except Exception as exc:
            logger.error("Failed to load full-market stock registry: %s", exc)
            return []

        limit = int(source.options.get("full_market_limit", 0) or 0)
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
                    logger.debug("  NOTIFY %s OK → %s", r.channel, r.target)
                else:
                    logger.warning(
                        "  NOTIFY %s FAILED → %s: %s",
                        r.channel,
                        r.target,
                        r.message,
                    )
        except Exception as e:
            logger.error("Notification dispatch error: %s", e)

    def run_loop(self, tier: str | None = None):
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

    def close(self):
        for source in self.sources.values():
            source.close()
        if self.state_store:
            self.state_store.close()
        if self.storage and hasattr(self.storage, "close"):
            self.storage.close()

    def _get_tier_config(self, tier: str | None) -> SchedulingTierConfig | None:
        if tier is None:
            return None
        for item in self.config.scheduling.tiers:
            if item.name == tier:
                return item
        raise ValueError(f"Unknown scheduling tier: {tier}")

    def _tier_interval_seconds(
        self,
        tier: SchedulingTierConfig,
        month: int | None = None,
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
        tier: SchedulingTierConfig | None,
    ) -> list[str] | None:
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
        tier_stock_codes: Sequence[str] | None,
    ) -> list[dict] | None:
        scfg = self.config.sources[name]
        if tier_stock_codes is None:
            return scfg.watchlist

        if source.name != "cninfo":
            return [
                entry for entry in scfg.watchlist if entry.get("stock", "") in set(tier_stock_codes)
            ]

        kinds = source.options.get("kinds", ["annual", "semi", "q1", "q3"])
        by_stock = {
            entry.get("stock", ""): dict(entry) for entry in scfg.watchlist if entry.get("stock")
        }
        watchlist: list[dict] = []
        missing_codes: list[str] = []
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
                logger.error(
                    "Source [%s]: failed to resolve tier stocks from registry: %s", name, exc
                )

        return watchlist
