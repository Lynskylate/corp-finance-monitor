"""Tests for SourceConfig.fetch_filter — kind + year_range filtering in engine fetch."""

import os
import shutil
import tempfile
import unittest

from corp_finance_monitor.core.config import (
    Config,
    EngineConfig,
    FetchFilterConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource


class _MultiKindSource(AbstractSource):
    """Source that discovers filings with different kinds and years."""

    def __init__(self, name, config):
        super().__init__(name, config)
        self.fetched_refs = []

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        return [
            FilingRef(
                source="test",
                source_id="annual-2025",
                stock_code="000001",
                kind=FilingKind.ANNUAL,
                published_at="2025-03-30",
                title="2025 Annual",
            ),
            FilingRef(
                source="test",
                source_id="q1-2026",
                stock_code="000001",
                kind=FilingKind.Q1,
                published_at="2026-04-28",
                title="2026 Q1",
            ),
            FilingRef(
                source="test",
                source_id="semi-2025",
                stock_code="000001",
                kind=FilingKind.SEMI,
                published_at="2025-08-20",
                title="2025 Semi",
            ),
            FilingRef(
                source="test",
                source_id="q3-2024",
                stock_code="000001",
                kind=FilingKind.Q3,
                published_at="2024-10-28",
                title="2024 Q3",
            ),
            FilingRef(
                source="test",
                source_id="annual-2024",
                stock_code="000001",
                kind=FilingKind.ANNUAL,
                published_at="2024-03-30",
                title="2024 Annual",
            ),
        ]

    def fetch(self, ref):
        self.fetched_refs.append(ref)
        return Filing(ref=ref, content=b"%PDF-1.4\nfiltered\n")


class FetchFilterConfigTest(unittest.TestCase):
    """Unit tests for FetchFilterConfig.matches()."""

    def test_empty_filter_matches_everything(self):
        ff = FetchFilterConfig()
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.ANNUAL, published_at="2025-01-01")
        self.assertTrue(ff.matches(ref))

    def test_kind_filter_passes_matching_kind(self):
        ff = FetchFilterConfig(kinds=["annual", "q1"])
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.ANNUAL, published_at="2025-01-01")
        self.assertTrue(ff.matches(ref))

    def test_kind_filter_rejects_non_matching_kind(self):
        ff = FetchFilterConfig(kinds=["annual", "q1"])
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.SEMI, published_at="2025-01-01")
        self.assertFalse(ff.matches(ref))

    def test_year_range_filter_passes_matching_year(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.ANNUAL, published_at="2025-03-30")
        self.assertTrue(ff.matches(ref))

    def test_year_range_filter_rejects_out_of_range(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.ANNUAL, published_at="2024-03-30")
        self.assertFalse(ff.matches(ref))

    def test_combined_kind_and_year_must_both_match(self):
        ff = FetchFilterConfig(kinds=["annual"], year_range=[2025, 2026])
        # kind matches but year doesn't
        ref1 = FilingRef(source="t", source_id="1", stock_code="000001",
                         kind=FilingKind.ANNUAL, published_at="2024-03-30")
        self.assertFalse(ff.matches(ref1))
        # year matches but kind doesn't
        ref2 = FilingRef(source="t", source_id="2", stock_code="000001",
                         kind=FilingKind.Q1, published_at="2025-04-28")
        self.assertFalse(ff.matches(ref2))
        # both match
        ref3 = FilingRef(source="t", source_id="3", stock_code="000001",
                         kind=FilingKind.ANNUAL, published_at="2025-03-30")
        self.assertTrue(ff.matches(ref3))

    def test_missing_published_at_rejected_by_year_filter(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(source="t", source_id="1", stock_code="000001",
                        kind=FilingKind.ANNUAL, published_at="")
        self.assertFalse(ff.matches(ref))


class FetchFilterEngineTest(unittest.TestCase):
    """Integration tests: engine respects fetch_filter on a source."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_config(self, fetch_filter=None):
        return Config(
            engine=EngineConfig(run_once=True, fetch_delay_seconds=0),
            storage=StorageConfig(
                backend="disk",
                base_dir=os.path.join(self.tmpdir, "data"),
            ),
            state_store=StateStoreConfig(
                backend="sqlite",
                path=os.path.join(self.tmpdir, "data", ".cfm_state", "state.db"),
            ),
            sources={
                "test": SourceConfig(
                    name="test",
                    watchlist=[],
                    fetch_filter=fetch_filter,
                ),
            },
        )

    def test_no_filter_fetches_all(self):
        cfg = self._make_config(fetch_filter=None)
        engine = Engine(cfg, {"test": _MultiKindSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            self.assertEqual(stats["discovered"], 5)
            self.assertEqual(stats["fetched"], 5)
            self.assertEqual(stats["failed"], 0)
        finally:
            engine.close()

    def test_filter_annual_and_q1_for_2025_2026(self):
        cfg = self._make_config(
            fetch_filter=FetchFilterConfig(
                kinds=["annual", "q1"],
                year_range=[2025, 2026],
            )
        )
        engine = Engine(cfg, {"test": _MultiKindSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            # Should discover 5 but only fetch: annual-2025, q1-2026
            self.assertEqual(stats["discovered"], 2)
            self.assertEqual(stats["fetched"], 2)
            self.assertEqual(stats["failed"], 0)
            fetched_ids = [r.source_id for r in engine.sources["test"].fetched_refs]
            self.assertIn("annual-2025", fetched_ids)
            self.assertIn("q1-2026", fetched_ids)
            self.assertNotIn("semi-2025", fetched_ids)
            self.assertNotIn("q3-2024", fetched_ids)
            self.assertNotIn("annual-2024", fetched_ids)
        finally:
            engine.close()

    def test_filter_kind_only(self):
        cfg = self._make_config(
            fetch_filter=FetchFilterConfig(kinds=["annual"])
        )
        engine = Engine(cfg, {"test": _MultiKindSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            # annual-2025 and annual-2024
            self.assertEqual(stats["discovered"], 2)
            self.assertEqual(stats["fetched"], 2)
        finally:
            engine.close()

    def test_filter_year_only(self):
        cfg = self._make_config(
            fetch_filter=FetchFilterConfig(year_range=[2025, 2026])
        )
        engine = Engine(cfg, {"test": _MultiKindSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            # annual-2025, q1-2026, semi-2025
            self.assertEqual(stats["discovered"], 3)
            self.assertEqual(stats["fetched"], 3)
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
