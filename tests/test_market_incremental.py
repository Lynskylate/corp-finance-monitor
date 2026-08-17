"""
Contract tests for market-level incremental discovery (options.incremental_mode: market).

Why this exists (2026-08-17 incident): the scheduled run loop's full tier walks
per-stock checkpoints, and scan_progress has no TTL — once bootstrap completes
the full tier goes permanently silent. From 06-20 to 08-17 only 8 of 1,258
scheduler rounds discovered anything (all 3-stock watchlist hits); every bulk
dataset came from manual one-shot syncs. The market-level mode makes the
scheduled loop discover new disclosures with a market-wide `since`-window
query: O(#columns) API calls per round.

Invariants pinned here:
  1. A disclosure published after the last successful run MUST be discovered
     by the next scheduled round — even when every stock is already marked
     done in scan_progress.
  2. Market mode is scheduled-loop-only: explicit `sync` (tier=None) keeps the
     per-stock path (it is the bootstrap/backfill tool).
  3. Market mode requires a since window; windowless runs fall back to the
     per-stock path.
  4. A failed market discover MUST record a failed run so
     last_successful_run_start does not advance past the missed window.
  5. Market rounds never write scan_progress (checkpoints belong to per-stock
     scans; mixing them would corrupt resume semantics).
  6. Off by default: without the option, the legacy path is used.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from corp_finance_monitor.core.config import (
    Config,
    EngineConfig,
    SchedulingTierConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource


class _MarketSource(AbstractSource):
    """Fake source: per-stock discover always reports it ran; discover_market
    returns one new filing (or raises if configured)."""

    def __init__(self, name, config, market_refs=None, market_error=False):
        super().__init__(name, config)
        self.market_refs = market_refs if market_refs is not None else []
        self.market_error = market_error
        self.calls = {"discover": 0, "discover_market": 0, "market_since": []}

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        self.calls["discover"] += 1
        return []

    def discover_market(self, since):
        self.calls["discover_market"] += 1
        self.calls["market_since"].append(since)
        if self.market_error:
            raise RuntimeError("market query failed")
        return list(self.market_refs)

    def fetch(self, ref):
        return Filing(ref=ref, content=b"%PDF-1.4\nmarket\n")


def _new_ref(code="300012", ann_id="1222800001"):
    return FilingRef(
        source="cninfo",
        source_id=ann_id,
        stock_code=code,
        title="2026年半年度报告",
        kind=FilingKind.SEMI,
        published_at="2026-08-17",
        url=f"https://example.com/{ann_id}.pdf",
    )


class MarketIncrementalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_market_inc_")
        self.config = Config(
            engine=EngineConfig(
                run_once=True,
                interval_minutes=360,
                concurrency=1,
                fetch_delay_seconds=0,
            ),
            scheduling=None,
            storage=StorageConfig(backend="disk", base_dir=os.path.join(self.tmpdir, "data")),
            state_store=StateStoreConfig(
                backend="sqlite",
                path=os.path.join(self.tmpdir, "data", ".cfm_state", "state.db"),
            ),
            sources={
                "cninfo": SourceConfig(
                    name="cninfo",
                    watchlist=[],
                    options={
                        "full_market": True,
                        "incremental_mode": "market",
                    },
                ),
            },
        )
        # scheduling config is constructed separately because Config's
        # dataclass default is a list; keep tiers explicit here.
        from corp_finance_monitor.core.config import SchedulingConfig

        self.config.scheduling = SchedulingConfig(
            tiers=[
                SchedulingTierConfig(name="core", stocks=["000725"], interval_minutes=60),
                SchedulingTierConfig(name="full", interval_minutes=720, use_registry=True),
            ]
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _engine(self, source):
        # Engine instantiates registry entries as classes: cls(name, scfg).
        # Pass a factory returning the pre-built fake instance so calls/refs
        # are observable by the test.
        engine = Engine(self.config, {"cninfo": lambda name, scfg: source})
        engine.initialize()
        return engine

    def _mark_all_done(self, engine, codes=("300012", "000725")):
        for code in codes:
            engine.state_store.mark_scan_done("cninfo", code)

    def test_new_filing_found_next_round_despite_completed_checkpoints(self):
        """Invariant 1: new disclosure after last run is discovered even when
        scan_progress is fully done (the June-Aug silent-loop failure mode)."""
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_refs=[_new_ref()])
        engine = self._engine(source)
        self._mark_all_done(engine)

        # A prior successful run establishes the incremental window.
        engine.state_store.record_run(
            "2026-08-16T00:00:00.000000", "2026-08-16T00:01:00.000000", 0, 0, 0
        )

        stats = engine.run_once(tier="full")

        self.assertEqual(source.calls["discover_market"], 1)
        self.assertEqual(source.calls["discover"], 0)
        self.assertEqual(stats["discovered"], 1)
        self.assertEqual(stats["fetched"], 1)
        # window resolved from last successful run start (date-truncated)
        self.assertEqual(source.calls["market_since"], ["2026-08-16"])
        engine.close()

    def test_explicit_sync_keeps_per_stock_path(self):
        """Invariant 2: tier=None (the `sync` CLI / backfill tool) must not use
        market mode even when the option is set."""
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_refs=[_new_ref()])
        engine = self._engine(source)
        engine.run_once(since="2026-08-16", tier=None)
        self.assertEqual(source.calls["discover_market"], 0)
        self.assertGreaterEqual(source.calls["discover"], 1)
        engine.close()

    def test_windowless_run_falls_back_to_per_stock(self):
        """Invariant 3: since='full' (bootstrap semantics) uses per-stock path."""
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_refs=[_new_ref()])
        engine = self._engine(source)
        engine.run_once(since="full", tier="full")
        self.assertEqual(source.calls["discover_market"], 0)
        self.assertGreaterEqual(source.calls["discover"], 1)
        engine.close()

    def test_failed_market_discover_records_failed_run(self):
        """Invariant 4: a failed market query must not advance
        last_successful_run_start past the missed window."""
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_error=True)
        engine = self._engine(source)

        engine.state_store.record_run(
            "2026-08-16T00:00:00.000000", "2026-08-16T00:01:00.000000", 0, 0, 0
        )
        stats = engine.run_once(tier="full")
        self.assertEqual(stats["failed"], 1)

        # The failed run must not become the new incremental baseline.
        self.assertEqual(
            engine.state_store.last_successful_run_start(),
            "2026-08-16T00:00:00.000000",
        )
        engine.close()

    def test_market_round_does_not_touch_scan_progress(self):
        """Invariant 5: market rounds never write scan_progress."""
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_refs=[_new_ref()])
        engine = self._engine(source)
        engine.state_store.record_run(
            "2026-08-16T00:00:00.000000", "2026-08-16T00:01:00.000000", 0, 0, 0
        )
        engine.run_once(tier="full")
        done, _ = engine.state_store.count_scan_progress("cninfo")
        self.assertEqual(done, 0)
        engine.close()

    def test_off_by_default_uses_legacy_path(self):
        """Invariant 6: without incremental_mode the legacy path is used."""
        self.config.sources["cninfo"].options.pop("incremental_mode")
        source = _MarketSource("cninfo", self.config.sources["cninfo"], market_refs=[_new_ref()])
        engine = self._engine(source)
        engine.state_store.record_run(
            "2026-08-16T00:00:00.000000", "2026-08-16T00:01:00.000000", 0, 0, 0
        )
        engine.run_once(tier="full")
        self.assertEqual(source.calls["discover_market"], 0)
        engine.close()


class CninfoDiscoverMarketTestCase(unittest.TestCase):
    """Source-level contract for CninfoSource.discover_market."""

    def _source(self, kinds=None):
        options = {"full_market": True, "incremental_mode": "market"}
        if kinds:
            options["kinds"] = kinds
        return __import__(
            "corp_finance_monitor.sources.cninfo", fromlist=["CninfoSource"]
        ).CninfoSource("cninfo", SourceConfig(name="cninfo", watchlist=[], options=options))

    @staticmethod
    def _resp(items, has_more=False):
        m = MagicMock()
        m.json.return_value = {"announcements": items, "hasMore": has_more}
        return m

    @staticmethod
    def _ann(ann_id, code, title="2026年半年度报告", ts=1755400000000):
        return {
            "announcementId": ann_id,
            "secCode": code,
            "secName": "测试公司",
            "announcementTitle": title,
            "adjunctUrl": f"2026/08/17/{ann_id}.PDF",
            "announcementTime": ts,
        }

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    def test_queries_all_columns_and_dedupes(self, mock_post):
        # szse page1 (hasMore) -> page2; sse empty; bj returns a duplicate id
        responses = iter(
            [
                self._resp([self._ann("A1", "300012")], has_more=True),
                self._resp([self._ann("A2", "000712")]),
                self._resp([]),
                self._resp([self._ann("A1", "300012")]),  # duplicate across columns
            ]
        )
        mock_post.side_effect = lambda *a, **k: next(responses)

        refs = self._source().discover_market(since="2026-08-16")

        self.assertEqual(len(refs), 2)
        self.assertEqual({r.source_id for r in refs}, {"A1", "A2"})
        self.assertEqual({r.stock_code for r in refs}, {"300012", "000712"})
        columns = [call.kwargs["data"]["column"] for call in mock_post.call_args_list]
        self.assertEqual(columns, ["szse", "szse", "sse", "bj"])
        for call in mock_post.call_args_list:
            self.assertEqual(call.kwargs["data"]["stock"], "")
            self.assertTrue(call.kwargs["data"]["seDate"].startswith("2026-08-16~"))

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    def test_category_built_from_kinds(self, mock_post):
        mock_post.return_value = self._resp([])
        self._source(kinds=["forecast"]).discover_market(since="2026-08-16")
        sent = mock_post.call_args_list[0].kwargs["data"]["category"]
        self.assertEqual(sent, "category_yjygjxz_szsh")

    def test_requires_since_window(self):
        with self.assertRaises(ValueError):
            self._source().discover_market(since="")


if __name__ == "__main__":
    unittest.main()
