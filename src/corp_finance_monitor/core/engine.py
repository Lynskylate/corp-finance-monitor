from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Sequence

from .config import Config
from .model import FilingRef
from .source import AbstractSource
from .storage import AbstractStorage
from .state import AbstractStateStore

logger = logging.getLogger("cfm")


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
        self._source_registry = source_registry

    def initialize(self):
        """初始化: 创建存储、加载source、打开状态数据库"""
        self._init_storage()
        self._init_state_store()
        self._init_sources()

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

    def run_once(self, selected_sources: Optional[Sequence[str]] = None) -> Dict[str, int]:
        """
        执行一轮发现-下载流程。
        返回统计数据: {discovered, fetched, failed}
        """
        run_start = datetime.utcnow().isoformat()
        stats = {"discovered": 0, "fetched": 0, "failed": 0}
        selected = set(selected_sources or [])

        for name, source in self.sources.items():
            if selected and name not in selected:
                continue
            scfg = self.config.sources[name]
            logger.info("Source [%s]: discovering...", name)

            try:
                refs = source.discover(scfg.watchlist)
            except Exception as e:
                logger.error("Source [%s] discover failed: %s", name, e)
                continue

            stats["discovered"] += len(refs)
            logger.info("Source [%s]: discovered %d filing(s)", name, len(refs))

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
                    stats["fetched"] += 1
                except Exception as e:
                    logger.error("  FAILED: %s - %s", ref.title, e)
                    stats["failed"] += 1

                time.sleep(self.config.engine.fetch_delay_seconds)

        run_end = datetime.utcnow().isoformat()
        self.state_store.record_run(
            run_start,
            run_end,
            stats["discovered"],
            stats["fetched"],
            stats["failed"],
        )
        return stats

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
