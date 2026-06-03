"""Tests for Phase 5: scheduling tiers, disclosure windows, and tier-aware runs."""
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.conftest import SRC  # noqa: F401
from corp_finance_monitor.core.config import (
    Config,
    EngineConfig,
    SchedulingConfig,
    SchedulingTierConfig,
    DisclosureWindowConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.sources.stock_registry import StockEntry


class _RegistryBackedSource(AbstractSource):
    def __init__(self, name, config):
        super().__init__(name, config)
        self.discover_watchlists = []
        self.discover_only_codes = []
        self._registry = _FakeLookupRegistry(
            {
                "000725": StockEntry("000725", "org725", "京东方A", "SZSE", "A股"),
                "600519": StockEntry("600519", "org519", "贵州茅台", "SSE", "A股"),
                "000858": StockEntry("000858", "org858", "五粮液", "SZSE", "A股"),
            }
        )

    def _get_registry(self):
        return self._registry

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        self.discover_watchlists.append(list(watchlist or []))
        self.discover_only_codes.append(None if only_stock_codes is None else list(only_stock_codes))
        refs = []
        if only_stock_codes:
            stock_codes = list(only_stock_codes)
        else:
            stock_codes = [entry.get("stock", "") for entry in (watchlist or [])]
        for stock in stock_codes:
            refs.append(
                FilingRef(
                    source=self.name,
                    source_id=f"{self.name}-{stock}",
                    stock_code=stock,
                    title=f"{stock} filing",
                    kind=FilingKind.ANNUAL,
                    published_at="2025-01-01",
                    url="",
                )
            )
        return refs

    def fetch(self, ref):
        return Filing(ref=ref, content=b"%PDF-1.4\nsched\n")


class _FakeLookupRegistry:
    def __init__(self, entries):
        self._entries = entries

    def get_a_shares(self):
        return list(self._entries.values())

    def lookup(self, stock_code):
        return self._entries.get(stock_code)


class _LoopTestEngine(Engine):
    def __init__(self, config, source_registry):
        super().__init__(config, source_registry)
        self.run_calls = []
        self.stop_after = 0

    def run_once(self, selected_sources=None, since=None, resume=False, tier=None):
        self.run_calls.append(tier)
        if self.stop_after and len(self.run_calls) >= self.stop_after:
            raise StopIteration()
        return {"discovered": 0, "fetched": 0, "failed": 0}


class SchedulingConfigTestCase(unittest.TestCase):
    def test_parse_scheduling_from_file(self):
        with tempfile.TemporaryDirectory(prefix="cfm_sched_cfg_") as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    """
engine:
  run_once: true
scheduling:
  tiers:
    - name: core
      stocks: ["000725", "600519"]
      interval_minutes: 60
    - name: full
      interval_minutes: 720
      use_registry: true
  disclosure_windows:
    - months: [1, 2, 3, 4]
      multiplier: 0.5
"""
                )
            cfg = Config.from_file(path)
            self.assertEqual([tier.name for tier in cfg.scheduling.tiers], ["core", "full"])
            self.assertEqual(cfg.scheduling.tiers[0].stocks, ["000725", "600519"])
            self.assertTrue(cfg.scheduling.tiers[1].use_registry)
            self.assertEqual(cfg.scheduling.disclosure_windows[0].months, [1, 2, 3, 4])
            self.assertEqual(cfg.scheduling.disclosure_windows[0].multiplier, 0.5)


class SchedulingEngineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_sched_engine_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_config(self):
        return Config(
            engine=EngineConfig(
                run_once=True,
                interval_minutes=360,
                concurrency=1,
                fetch_delay_seconds=0,
            ),
            scheduling=SchedulingConfig(
                tiers=[
                    SchedulingTierConfig(
                        name="core",
                        stocks=["000725", "600519"],
                        interval_minutes=60,
                    ),
                    SchedulingTierConfig(
                        name="full",
                        interval_minutes=720,
                        use_registry=True,
                    ),
                ],
                disclosure_windows=[
                    DisclosureWindowConfig(months=[1, 2, 3, 4], multiplier=0.5),
                    DisclosureWindowConfig(months=[7, 8], multiplier=0.5),
                ],
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
                "cninfo": SourceConfig(
                    name="cninfo",
                    options={"full_market": False},
                    watchlist=[],
                ),
                "hkex": SourceConfig(
                    name="hkex",
                    watchlist=[
                        {"stock": "00700", "kinds": ["annual"]},
                        {"stock": "09988", "kinds": ["annual"]},
                    ],
                ),
            },
        )

    def test_core_tier_uses_registry_backed_watchlist_for_cninfo(self):
        engine = Engine(self._make_config(), {"cninfo": _RegistryBackedSource, "hkex": _RegistryBackedSource})
        engine.initialize()
        try:
            stats = engine.run_once(tier="core")
            self.assertEqual(stats["discovered"], 2)
            source = engine.sources["cninfo"]
            self.assertEqual(
                [entry["stock"] for entry in source.discover_watchlists[0]],
                ["000725", "600519"],
            )
            self.assertIsNone(source.discover_only_codes[0])
        finally:
            engine.close()

    def test_registry_source_skips_when_no_tier_matches(self):
        """Registry-backed source with no matching tier stocks skips entirely."""
        engine = Engine(self._make_config(), {"cninfo": _RegistryBackedSource, "hkex": _RegistryBackedSource})
        engine.initialize()
        try:
            stats = engine.run_once(tier="core", selected_sources=["hkex"])
            self.assertEqual(stats["discovered"], 0)
            hkex = engine.sources["hkex"]
            # discover() is never called because tier has no matching stocks
            self.assertEqual(hkex.discover_watchlists, [])
        finally:
            engine.close()

    def test_full_tier_uses_existing_full_market_path(self):
        cfg = self._make_config()
        cfg.sources["cninfo"].options["full_market"] = True
        cfg.engine.concurrency = 2
        engine = Engine(cfg, {"cninfo": _RegistryBackedSource, "hkex": _RegistryBackedSource})
        engine.initialize()
        try:
            stats = engine.run_once(tier="full", selected_sources=["cninfo"])
            self.assertEqual(stats["discovered"], 3)
            source = engine.sources["cninfo"]
            self.assertEqual(source.discover_only_codes[0], ["000725", "600519", "000858"])
        finally:
            engine.close()

    def test_disclosure_window_applies_smallest_multiplier(self):
        engine = Engine(self._make_config(), {"cninfo": _RegistryBackedSource, "hkex": _RegistryBackedSource})
        self.assertEqual(engine._tier_interval_seconds(engine.config.scheduling.tiers[0], month=2), 1800)
        self.assertEqual(engine._tier_interval_seconds(engine.config.scheduling.tiers[1], month=6), 43200)

    def test_run_loop_cycles_due_tiers(self):
        cfg = self._make_config()
        engine = _LoopTestEngine(cfg, {"cninfo": _RegistryBackedSource, "hkex": _RegistryBackedSource})
        engine.stop_after = 2
        with patch("corp_finance_monitor.core.engine.time.monotonic", side_effect=[0, 0, 0, 0, 1, 1]):
            with patch("corp_finance_monitor.core.engine.time.sleep", return_value=None):
                with self.assertRaises(StopIteration):
                    engine.run_loop()
        self.assertEqual(engine.run_calls, ["core", "full"])


if __name__ == "__main__":
    unittest.main()
