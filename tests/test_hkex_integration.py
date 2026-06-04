"""Integration tests for HKEX full_market config + engine pipeline (task #42).

Validates that the complete Engine → HKEXSource → HKEXStockRegistry pipeline
works end-to-end with production-like config: full_market=true, tier scheduling,
batched discover, fetch, and state persistence.
"""

import os
import shutil
import tempfile
import unittest

from corp_finance_monitor.core.config import (
    Config,
    DisclosureWindowConfig,
    EngineConfig,
    SchedulingConfig,
    SchedulingTierConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource


class _FakeHKEXRegistry:
    """Fake HKEX registry with get_stock_codes() + get_hk_stocks()."""

    def __init__(self, codes):
        self._codes = codes

    def get_stock_codes(self):
        return list(self._codes)

    def get_hk_stocks(self):
        from corp_finance_monitor.sources.hkex_registry import StockEntry as SE

        return [SE(stock_code=c, name=f"Stock {c}", exchange="SEHK") for c in self._codes]


class _HKEXIntegrationSource(AbstractSource):
    """Mock HKEX source with fake registry for integration testing."""

    def __init__(self, name, config):
        super().__init__(name, config)
        self.discover_calls = []
        self.fetched_refs = []
        self._registry = _FakeHKEXRegistry(
            ["00700", "09988", "02318", "01299", "00941"]
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
                    source=self.name,
                    source_id=f"{self.name}-{code}",
                    stock_code=code,
                    title=f"{code} annual report",
                    kind=FilingKind.ANNUAL,
                    published_at="2025-01-01",
                    url=f"https://example.com/{code}.pdf",
                )
            )
        return refs

    def fetch(self, ref):
        self.fetched_refs.append(ref)
        return Filing(ref=ref, content=b"%PDF-1.4\nhkex integration\n")


class HKEXIntegrationTestCase(unittest.TestCase):
    """Integration tests for HKEX full_market with engine pipeline."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_hkex_integ_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_config(self, full_market=True, batch_size=2, concurrency=3):
        """Build a production-like config with HKEX full_market enabled."""
        return Config(
            engine=EngineConfig(
                run_once=True,
                interval_minutes=360,
                concurrency=concurrency,
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
                        stocks=["00700", "09988", "02318", "01299", "00941"],
                    ),
                ],
                disclosure_windows=[
                    DisclosureWindowConfig(months=[1, 2, 3, 4], multiplier=0.5),
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
                    watchlist=[
                        {"stock": "000725", "kinds": ["annual"]},
                    ],
                ),
                "hkex": SourceConfig(
                    name="hkex",
                    options={
                        "full_market": full_market,
                        "full_market_batch_size": batch_size,
                        "kinds": ["annual"],
                    },
                    watchlist=[
                        {"stock": "00700", "kinds": ["annual"]},
                        {"stock": "09988", "kinds": ["annual"]},
                        {"stock": "02318", "kinds": ["annual"]},
                        {"stock": "01299", "kinds": ["annual"]},
                        {"stock": "00941", "kinds": ["annual"]},
                    ],
                ),
            },
        )

    def test_hkex_full_market_batched_discover_and_fetch(self):
        """End-to-end: engine batches HKEX stocks, discovers, and fetches."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _HKEXIntegrationSource, "hkex": _HKEXIntegrationSource})
        engine.initialize()
        try:
            stats = engine.run_once(tier="full", selected_sources=["hkex"])
            hkex = engine.sources["hkex"]

            # All 5 stocks discovered across 3 batches (size 2)
            self.assertEqual(stats["discovered"], 5)
            self.assertEqual(stats["fetched"], 5)
            self.assertEqual(stats["failed"], 0)

            # Batching: 2+2+1 = 5 stocks in 3 discover calls
            self.assertEqual(len(hkex.discover_calls), 3)
            self.assertEqual(hkex.discover_calls[0], ["00700", "09988"])
            self.assertEqual(hkex.discover_calls[1], ["02318", "01299"])
            self.assertEqual(hkex.discover_calls[2], ["00941"])

            # All 5 filings fetched
            self.assertEqual(len(hkex.fetched_refs), 5)
        finally:
            engine.close()

    def test_hkex_full_market_scan_progress_persisted(self):
        """Verify scan_progress is recorded for HKEX after full market run."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _HKEXIntegrationSource, "hkex": _HKEXIntegrationSource})
        engine.initialize()
        try:
            engine.run_once(tier="full", selected_sources=["hkex"])

            # Check scan_progress was persisted in state DB
            import sqlite3
            db_path = os.path.join(self.tmpdir, "data", ".cfm_state", "state.db")
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT stock_code, status FROM scan_progress WHERE source='hkex' ORDER BY stock_code"
            ).fetchall()
            conn.close()

            self.assertEqual(len(rows), 5)
            codes = [r[0] for r in rows]
            self.assertEqual(codes, ["00700", "00941", "01299", "02318", "09988"])
            self.assertTrue(all(r[1] == "done" for r in rows))
        finally:
            engine.close()

    def test_hkex_full_market_alongside_cninfo_watchlist(self):
        """HKEX full_market runs independently; cninfo uses watchlist-only on core tier."""
        from tests.test_scheduling import _RegistryBackedSource

        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _RegistryBackedSource, "hkex": _HKEXIntegrationSource})
        engine.initialize()
        try:
            # HKEX full tier only
            stats = engine.run_once(tier="full", selected_sources=["hkex"])
            self.assertEqual(stats["discovered"], 5)
            self.assertEqual(stats["fetched"], 5)

            hkex = engine.sources["hkex"]
            self.assertEqual(len(hkex.discover_calls), 3)
        finally:
            engine.close()

    def test_hkex_incremental_skips_already_scanned(self):
        """Second run skips stocks already in scan_progress."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _HKEXIntegrationSource, "hkex": _HKEXIntegrationSource})
        engine.initialize()
        try:
            # First run
            stats1 = engine.run_once(tier="full", selected_sources=["hkex"])
            self.assertEqual(stats1["discovered"], 5)

            # Second run — all stocks already scanned, should be skipped
            hkex = engine.sources["hkex"]
            hkex.discover_calls.clear()
            hkex.fetched_refs.clear()

            stats2 = engine.run_once(tier="full", selected_sources=["hkex"])
            self.assertEqual(stats2["discovered"], 0)
            self.assertEqual(len(hkex.discover_calls), 0)
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
