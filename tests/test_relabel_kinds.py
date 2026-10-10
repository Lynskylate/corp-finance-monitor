"""Tests for the one-shot kind relabel maintenance (core/relabel.py + CLI).

背景（2026-10 预告季事故第二失效面）：变体标题（预增/快报措辞，缺「业绩预告」
四字）在旧分类器下被 Q1/Q3 子串规则兜住 → 以错误 kind 静默入库（prod 实测
q1=28 / q3=1）；engine 对 already_fetched 的 replay 走 skip 路径不重分类，
故需要一次性 relabel 工具。契约（#corp-finance-monitor:95cb6f79 +
SuperMan GO msg 38f8f671 + janny 3 点）：

1. 行级 oracle：验收 = source_id 集合逐一匹配独立清单，不是计数匹配；
2. scope 不变量：diff ⊆ 标题命中 FORECAST/EXPRESS 标记的行——非标记行在
   compute_relabel_plan 里无条件跳过，不变量在代码里成立（下方有反例钉死）；
3. 机械契约：dry-run 默认、--apply 执行、apply 后幂等（重算 plan 必空）。
"""

import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO

from corp_finance_monitor.cli.main import cmd_relabel_kinds
from corp_finance_monitor.core.config import StateStoreConfig
from corp_finance_monitor.core.model import FilingKind, FilingRef
from corp_finance_monitor.core.relabel import (
    compute_relabel_plan,
    title_matches_marker,
)
from corp_finance_monitor.sources.cninfo import _detect_kind
from corp_finance_monitor.state.sqlite import SQLiteStateStore

# ---------------------------------------------------------------------------
# 分类 ordering 钉（SuperMan/janny 契约点 2：必须含负例）
# 变体标记检查先于 Q1/Q3 子串规则——修复前这些标题被子串规则抢走。
# ---------------------------------------------------------------------------

# 生产实锭（603228 景旺电子 = source_id 1225599436，DB 里现存的 q3=1
# 误档行，title 原文）
JINGWANG_TITLE = "景旺电子2026年第三季度业绩预增公告"

# 生产实锭（600176 中国巨石，annId=1225598758——janny msg 623826ee 钉的
# 第 5 个丢弃件标题措辞样本）
JUSHI_TITLE = "中国巨石股份有限公司2026年前三季度业绩预增公告"


class TestVariantOrderingPins(unittest.TestCase):
    """变体标记必须赢过 Q1/Q3 子串规则；真季报负例必须保持原分类。"""

    def test_jingwang_real_title_forecast_not_q3(self):
        # prod q3=1 就是这一行：含「第三季度」但为预增公告
        self.assertEqual(_detect_kind(JINGWANG_TITLE), FilingKind.FORECAST)

    def test_q1_variant_forecast_not_q1(self):
        self.assertEqual(_detect_kind("2026年第一季度业绩预减公告"), FilingKind.FORECAST)

    def test_express_with_q3_substring_express_not_q3(self):
        # 同时含「第三季度」与「业绩快报」：快报必须赢
        self.assertEqual(_detect_kind("2026年第三季度业绩快报公告"), FilingKind.EXPRESS)

    def test_real_express_gap_title(self):
        # 600882 妙可蓝多实锭（annId=1225597946，G3 清单里的 express 件）
        self.assertEqual(_detect_kind("2026年前三季度业绩快报公告"), FilingKind.EXPRESS)

    def test_dual_marker_title_classifies_forecast(self):
        # 45 行口径的机理核心（janny msg 8c9676f7 / SuperMan dc7f40f0）：
        # 现库 19 条 kind=forecast 且含「业绩快报」的标题全部双 marker
        # （业绩快报 + 业绩预告，如 1225067320）。FORECAST-first 顺序下保持
        # forecast —— 零行从 forecast 迁出的前提。
        self.assertEqual(
            _detect_kind("2025年度业绩快报暨业绩预告更正公告"),
            FilingKind.FORECAST,
        )
        self.assertEqual(
            _detect_kind("…2025年度业绩快报暨2026年一季度业绩预告"),
            FilingKind.FORECAST,
        )

    # --- 负例：真季报不受标记规则影响 ---

    def test_negative_real_q3_report_stays_q3(self):
        self.assertEqual(_detect_kind("2026年第三季度报告"), FilingKind.Q3)

    def test_negative_real_q1_report_stays_q1(self):
        self.assertEqual(_detect_kind("2025年一季度报告"), FilingKind.Q1)


# ---------------------------------------------------------------------------
# compute_relabel_plan 单元：scope 不变量 + 行级内容 + 确定性排序
# ---------------------------------------------------------------------------


def _row(
    source_id,
    title,
    kind,
    source="cninfo",
    stock_code="600000",
    published_at="2026-10-08",
    unique_key=None,
):
    return {
        "unique_key": unique_key or f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "stock_code": stock_code,
        "title": title,
        "kind": kind,
        "published_at": published_at,
    }


class TestComputeRelabelPlan(unittest.TestCase):
    def test_variant_q3_row_planned_to_forecast(self):
        plan = compute_relabel_plan([_row("1225000001", JINGWANG_TITLE, "q3", stock_code="603228")])
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].from_kind, "q3")
        self.assertEqual(plan[0].to_kind, "forecast")
        self.assertEqual(plan[0].stock_code, "603228")
        self.assertEqual(plan[0].source_id, "1225000001")

    def test_express_worded_q1_row_planned_to_express(self):
        # prod 实锭（1225098400「2026年第一季度业绩快报」型，q1→express 15 行
        # 的样本）：含「第一季度」但快报标记必须赢
        plan = compute_relabel_plan([_row("1225098400", "2026年第一季度业绩快报", "q1")])
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].from_kind, "q1")
        self.assertEqual(plan[0].to_kind, "express")

    def test_dual_marker_forecast_row_stays_forecast_not_planned(self):
        # 显式不变量（SuperMan dc7f40f0 升格）：零行从 forecast 迁出。
        # 机理：双 marker 标题 FORECAST-first → _detect_kind=forecast=存量
        # kind → agreeing → 不进 plan。
        plan = compute_relabel_plan(
            [
                _row("1225067320", "2025年度业绩快报暨业绩预告更正公告", "forecast"),
                _row("1225157989", "…2025年度业绩快报暨2026年一季度业绩预告", "forecast"),
            ]
        )
        self.assertEqual(plan, [])

    def test_agreeing_kind_not_planned(self):
        plan = compute_relabel_plan([_row("1225000003", JUSHI_TITLE, "forecast")])
        self.assertEqual(plan, [])

    def test_non_marker_row_never_planned_even_if_kind_differs(self):
        # scope 不变量反例：标题不命中任何标记 → 即使 kind 与目标分类不一致
        # 也不进 plan（修复后 _detect_kind 对它返回 q3，与存量 annual 不同，
        # 工具仍然必须跳过——本命令不修非变体问题）。
        plan = compute_relabel_plan([_row("1225000004", "2026年第三季度报告", "annual")])
        self.assertEqual(plan, [])

    def test_mixed_rows_only_marker_mismatches_planned(self):
        rows = [
            _row("a-1", JINGWANG_TITLE, "q3"),
            _row("a-2", "2025年度业绩快报公告", "semi"),
            _row("a-3", JUSHI_TITLE, "forecast"),  # agrees → skipped
            _row("a-4", "2026年半年度报告", "annual"),  # non-marker → skipped
        ]
        plan = compute_relabel_plan(rows)
        # 同 source 同 published_at → 按 source_id 升序
        self.assertEqual([r.source_id for r in plan], ["a-1", "a-2"])
        self.assertEqual([r.to_kind for r in plan], ["forecast", "express"])

    def test_deterministic_ordering(self):
        rows = [
            _row("zz", JINGWANG_TITLE, "q3", published_at="2026-01-02"),
            _row("mm", JUSHI_TITLE, "q1", published_at="2026-01-01"),
            _row("aa", JUSHI_TITLE, "q1", published_at="2026-01-01", source="sse"),
        ]
        plan = compute_relabel_plan(rows)
        # sort key = (source, published_at, source_id)
        self.assertEqual(
            [(r.source, r.published_at, r.source_id) for r in plan],
            [
                ("cninfo", "2026-01-01", "mm"),
                ("cninfo", "2026-01-02", "zz"),
                ("sse", "2026-01-01", "aa"),
            ],
        )

    def test_title_matches_marker(self):
        self.assertTrue(title_matches_marker(JINGWANG_TITLE))
        self.assertTrue(title_matches_marker("2025年度业绩快报"))
        self.assertFalse(title_matches_marker("2026年第三季度报告"))
        self.assertFalse(title_matches_marker(""))


# ---------------------------------------------------------------------------
# SQLiteStateStore roundtrip：plan → update_filing_kinds → 重算必空（幂等）
# ---------------------------------------------------------------------------


def _ref(source_id, title, kind, stock_code="600000", published_at="2026-10-08"):
    return FilingRef(
        source="cninfo",
        source_id=source_id,
        stock_code=stock_code,
        title=title,
        kind=kind,
        published_at=published_at,
    )


class TestSqliteRelabelRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = SQLiteStateStore(
            StateStoreConfig(
                backend="sqlite",
                path=os.path.join(self.tmpdir, "state.db"),
            )
        )
        self.store.initialize()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_relabel_roundtrip_idempotent(self):
        self.store.record_filing(
            _ref("1225000011", JINGWANG_TITLE, FilingKind.Q3, stock_code="603228"),
            "/tmp/11.pdf",
        )
        self.store.record_filing(
            _ref("1225000012", "2025年度业绩快报公告", FilingKind.SEMI),
            "/tmp/12.pdf",
        )
        self.store.record_filing(
            _ref("1225000013", "2026年半年度报告", FilingKind.SEMI),
            "/tmp/13.pdf",
        )

        rows = self.store.list_filing_kind_rows()
        self.assertEqual(len(rows), 3)

        plan = compute_relabel_plan(rows)
        self.assertEqual({r.source_id for r in plan}, {"1225000011", "1225000012"})

        changed = self.store.update_filing_kinds([(r.to_kind, r.unique_key) for r in plan])
        self.assertEqual(changed, 2)

        # apply 后重算 plan 必空 —— 幂等契约
        self.assertEqual(compute_relabel_plan(self.store.list_filing_kind_rows()), [])

    def test_update_filing_kinds_empty_is_noop(self):
        self.assertEqual(self.store.update_filing_kinds([]), 0)


# ---------------------------------------------------------------------------
# CLI cmd_relabel_kinds：dry-run 默认 / --apply / 非 sqlite backend 拒绝
# ---------------------------------------------------------------------------


class TestCmdRelabelKinds(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "state.db")
        self.config_path = os.path.join(self.tmpdir, "config.yaml")
        with open(self.config_path, "w") as f:
            f.write(f"state_store:\n  backend: sqlite\n  path: {self.db_path}\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed(self):
        store = SQLiteStateStore(StateStoreConfig(backend="sqlite", path=self.db_path))
        store.initialize()
        store.record_filing(
            _ref("1225000021", JINGWANG_TITLE, FilingKind.Q3, stock_code="603228"),
            "/tmp/21.pdf",
        )
        store.record_filing(
            _ref("1225000022", "2026年第一季度业绩快报", FilingKind.Q1),
            "/tmp/22.pdf",
        )
        # 双 marker 行：FORECAST-first 下与存量 kind 一致 → 不进 plan
        store.record_filing(
            _ref(
                "1225000023",
                "2025年度业绩快报暨业绩预告更正公告",
                FilingKind.FORECAST,
            ),
            "/tmp/23.pdf",
        )
        store.close()

    def _run(self, apply=False):
        out = StringIO()
        args = Namespace(config=self.config_path, apply=apply, verbose=False)
        with redirect_stdout(out):
            cmd_relabel_kinds(args)
        return out.getvalue()

    def _stored_kinds(self):
        store = SQLiteStateStore(StateStoreConfig(backend="sqlite", path=self.db_path))
        store.initialize()
        try:
            rows = store.list_filing_kind_rows()
            return {r["source_id"]: r["kind"] for r in rows}
        finally:
            store.close()

    def test_dry_run_default_modifies_nothing(self):
        self._seed()
        out = self._run(apply=False)
        self.assertIn("Dry run only", out)
        self.assertIn(f"State DB: {self.db_path}", out)  # 解析路径可见（防指错库静默 0 行）
        self.assertIn("1225000021", out)  # 行级 diff 必须列出 source_id
        self.assertIn("q3 -> forecast", out)
        self.assertIn("q1 -> express", out)
        self.assertNotIn("forecast ->", out)  # 零行从 forecast 迁出
        # DB 未被修改
        self.assertEqual(
            self._stored_kinds(),
            {
                "1225000021": "q3",
                "1225000022": "q1",
                "1225000023": "forecast",
            },
        )

    def test_apply_updates_and_second_run_is_empty(self):
        self._seed()
        out = self._run(apply=True)
        self.assertIn("Applied: 2 rows updated.", out)
        self.assertIn("Verified: recomputed plan is empty (idempotent).", out)
        self.assertEqual(
            self._stored_kinds(),
            {
                "1225000021": "forecast",
                "1225000022": "express",
                "1225000023": "forecast",
            },
        )

        # 第二次执行（即使再 --apply）：0 行、仍幂等
        out2 = self._run(apply=True)
        self.assertIn("Relabel plan (0 rows)", out2)
        self.assertIn("Applied: 0 rows updated.", out2)

    def test_non_sqlite_backend_rejected(self):
        cfg_path = os.path.join(self.tmpdir, "pg.yaml")
        with open(cfg_path, "w") as f:
            f.write("state_store:\n  backend: postgres\n  path: /dev/null\n")
        args = Namespace(config=cfg_path, apply=False, verbose=False)
        with redirect_stdout(StringIO()), self.assertRaises(SystemExit) as ctx:
            cmd_relabel_kinds(args)
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
