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
from corp_finance_monitor.sources.cninfo import _detect_kind


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
        ref = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2025-01-01",
        )
        self.assertTrue(ff.matches(ref))

    def test_kind_filter_passes_matching_kind(self):
        ff = FetchFilterConfig(kinds=["annual", "q1"])
        ref = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2025-01-01",
        )
        self.assertTrue(ff.matches(ref))

    def test_kind_filter_rejects_non_matching_kind(self):
        ff = FetchFilterConfig(kinds=["annual", "q1"])
        ref = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.SEMI,
            published_at="2025-01-01",
        )
        self.assertFalse(ff.matches(ref))

    def test_year_range_filter_passes_matching_year(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2025-03-30",
        )
        self.assertTrue(ff.matches(ref))

    def test_year_range_filter_rejects_out_of_range(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2024-03-30",
        )
        self.assertFalse(ff.matches(ref))

    def test_combined_kind_and_year_must_both_match(self):
        ff = FetchFilterConfig(kinds=["annual"], year_range=[2025, 2026])
        # kind matches but year doesn't
        ref1 = FilingRef(
            source="t",
            source_id="1",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2024-03-30",
        )
        self.assertFalse(ff.matches(ref1))
        # year matches but kind doesn't
        ref2 = FilingRef(
            source="t",
            source_id="2",
            stock_code="000001",
            kind=FilingKind.Q1,
            published_at="2025-04-28",
        )
        self.assertFalse(ff.matches(ref2))
        # both match
        ref3 = FilingRef(
            source="t",
            source_id="3",
            stock_code="000001",
            kind=FilingKind.ANNUAL,
            published_at="2025-03-30",
        )
        self.assertTrue(ff.matches(ref3))

    def test_missing_published_at_rejected_by_year_filter(self):
        ff = FetchFilterConfig(year_range=[2025, 2026])
        ref = FilingRef(
            source="t", source_id="1", stock_code="000001", kind=FilingKind.ANNUAL, published_at=""
        )
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
        cfg = self._make_config(fetch_filter=FetchFilterConfig(kinds=["annual"]))
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
        cfg = self._make_config(fetch_filter=FetchFilterConfig(year_range=[2025, 2026]))
        engine = Engine(cfg, {"test": _MultiKindSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            # annual-2025, q1-2026, semi-2025
            self.assertEqual(stats["discovered"], 3)
            self.assertEqual(stats["fetched"], 3)
        finally:
            engine.close()


# ---------------------------------------------------------------------------
# 2026-10-09 SSE 预告季缺口回归（SuperMan G1 #2）
#
# 事故路径：沪主板公司预告季惯用「业绩预增公告」/「业绩快报公告」措辞，
# _detect_kind 修复前仅认「业绩预告」→ 缺口件落入 OTHER → 生产 fetch_filter
# （kinds=[annual,semi,q1,q3,forecast]）在 fetch 前丢弃（engine.py:216）。
# 该丢弃不计 failed、不落库、仅留 "fetch_filter skipped N refs" 日志——
# 连续两天每轮出现而无人察觉。本组测试钉死：混合标题窗口在生产 filter 下
# 零静默丢弃。
# ---------------------------------------------------------------------------

# 生产 filter 目标态（config 侧变更：/srv/projects/corp-finance-monitor/
# config/config.yaml 的 cninfo.fetch_filter.kinds 增加 express，与镜像同链部署）
PRODUCTION_FETCH_FILTER_KINDS = ["annual", "semi", "q1", "q3", "forecast", "express"]

# 2026-10-09 缺口 4 件的真实标题（announcementId 即 janny 验收判据）
REAL_GAP_TITLES = [
    ("1225595334", "600521", "浙江华海药业股份有限公司2026年前三季度业绩预增公告"),
    ("1225596445", "600256", "广汇能源股份有限公司2026年前三季度业绩预增公告"),
    ("1225597543", "605020", "浙江永和制冷股份有限公司2026年前三季度业绩预增公告"),
    ("1225597946", "600882", "2026年前三季度业绩快报公告"),
]


class _Q3ForecastWindowSource(AbstractSource):
    """模拟 discover_market 窗口：1 件已入库预告件 + 4 件缺口件。

    kind 由真实标题经 _detect_kind 分类——分类→过滤→fetch 全链路即事故路径。
    """

    def __init__(self, name, config):
        super().__init__(name, config)
        self.fetched_refs = []

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        titles = [("1225595001", "300389", "2026年前三季度业绩预告"), *REAL_GAP_TITLES]
        return [
            FilingRef(
                source="test",
                source_id=sid,
                stock_code=code,
                title=title,
                kind=_detect_kind(title),
                published_at="2026-10-08",
            )
            for sid, code, title in titles
        ]

    def fetch(self, ref):
        self.fetched_refs.append(ref)
        return Filing(ref=ref, content=b"%PDF-1.4\nregression window\n")


class TestForecastExpressWindowZeroSilentDrop(unittest.TestCase):
    """预增+快报+预告混合窗口，生产 fetch_filter.kinds 下全部放行、零静默丢弃。"""

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

    def test_production_filter_zero_silent_drop(self):
        cfg = self._make_config(
            fetch_filter=FetchFilterConfig(
                kinds=PRODUCTION_FETCH_FILTER_KINDS,
                year_range=[2025, 2026],
            )
        )
        engine = Engine(cfg, {"test": _Q3ForecastWindowSource})
        engine.initialize()
        try:
            stats = engine.run_once()
            # 5 件全部放行：任何一件被 filter 静默丢弃都会使 discovered < 5
            self.assertEqual(stats["discovered"], 5)
            self.assertEqual(stats["fetched"], 5)
            self.assertEqual(stats["failed"], 0)

            fetched = engine.sources["test"].fetched_refs
            self.assertEqual(
                {r.source_id for r in fetched},
                {
                    "1225595001",
                    "1225595334",
                    "1225596445",
                    "1225597543",
                    "1225597946",
                },
            )

            # kind-aware（SuperMan G3 验收口径）：3 预增落 forecast，快报落 express
            by_id = {r.source_id: r.kind for r in fetched}
            self.assertEqual(by_id["1225595334"], FilingKind.FORECAST)
            self.assertEqual(by_id["1225596445"], FilingKind.FORECAST)
            self.assertEqual(by_id["1225597543"], FilingKind.FORECAST)
            self.assertEqual(by_id["1225597946"], FilingKind.EXPRESS)
            self.assertEqual(by_id["1225595001"], FilingKind.FORECAST)

            # express 存储 + 状态链路 roundtrip（G1 #4 存储侧）
            for ref in fetched:
                self.assertTrue(engine.storage.exists(ref), f"{ref.source_id} not stored")
                self.assertTrue(engine.state_store.has_filing(ref), f"{ref.source_id} not in state")
        finally:
            engine.close()

    def test_filter_unit_all_real_gap_titles_pass(self):
        # 最小复现（不经 engine）：真实标题 → _detect_kind → 生产 filter，
        # 逐一断言放行——修复前这 4 件在这里全部 False。
        ff = FetchFilterConfig(
            kinds=PRODUCTION_FETCH_FILTER_KINDS,
            year_range=[2025, 2026],
        )
        for sid, code, title in REAL_GAP_TITLES:
            ref = FilingRef(
                source="test",
                source_id=sid,
                stock_code=code,
                title=title,
                kind=_detect_kind(title),
                published_at="2026-10-08",
            )
            self.assertTrue(ff.matches(ref), f"{sid} {title} silently dropped by filter")


if __name__ == "__main__":
    unittest.main()
