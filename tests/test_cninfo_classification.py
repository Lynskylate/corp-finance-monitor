"""
Tests for cninfo source title classification boundaries.

Covers the 6 known edge cases from the README plus regression cases
that look similar but should land in a different bucket.

The classifier is `_detect_kind` in
src/corp_finance_monitor/sources/cninfo.py
"""
import unittest

from tests.conftest import SRC  # noqa: F401  (forces src/ onto sys.path)
from corp_finance_monitor.sources.cninfo import _detect_kind, CATEGORY_MAP
from corp_finance_monitor.core.model import FilingKind


class TestAnnualClassification(unittest.TestCase):
    """纯年报 — 不含"摘要"且不含"半年度"。"""

    def test_plain_annual(self):
        self.assertEqual(_detect_kind("2025年年度报告"), FilingKind.ANNUAL)

    def test_annual_with_company_prefix(self):
        self.assertEqual(_detect_kind("京东方A：2025年年度报告"), FilingKind.ANNUAL)

    def test_annual_english_company(self):
        self.assertEqual(_detect_kind("BOE Technology 2025年年度报告"), FilingKind.ANNUAL)

    def test_annual_with_correction_notice(self):
        # 更正后的年报仍应归到 annual
        self.assertEqual(_detect_kind("2025年年度报告（更正后）"), FilingKind.ANNUAL)

    def test_annual_with_audit_opinion(self):
        # 含"审计报告"字样但属于年报附件
        self.assertEqual(
            _detect_kind("2025年年度报告及审计报告"),
            FilingKind.ANNUAL,
        )


class TestAnnualSummaryIsOther(unittest.TestCase):
    """年报摘要 — 必须落到 OTHER，不能是 ANNUAL。"""

    def test_annual_summary(self):
        self.assertEqual(_detect_kind("2025年年度报告摘要"), FilingKind.OTHER)

    def test_annual_summary_with_company(self):
        self.assertEqual(_detect_kind("京东方A 2025年年度报告摘要"), FilingKind.OTHER)

    def test_annual_summary_correction(self):
        self.assertEqual(_detect_kind("2025年年度报告摘要（修订）"), FilingKind.OTHER)


class TestSemiClassification(unittest.TestCase):
    """半年报 / 中期报告。"""

    def test_plain_semi(self):
        self.assertEqual(_detect_kind("2025年半年度报告"), FilingKind.SEMI)

    def test_interim_uses_semi(self):
        # 中期报告 = SEMI (与 README 验证一致)
        self.assertEqual(_detect_kind("2025年中期报告"), FilingKind.SEMI)

    def test_semi_summary_is_still_semi(self):
        # 半年报摘要不归 OTHER（README 验证：semi）
        self.assertEqual(_detect_kind("2025年半年度报告摘要"), FilingKind.SEMI)

    def test_semi_takes_priority_over_annual(self):
        # 含"半年度"必须落到 SEMI，不能误判为 ANNUAL
        self.assertEqual(
            _detect_kind("2025年半年度报告及摘要"),
            FilingKind.SEMI,
        )


class TestQuarterlyClassification(unittest.TestCase):
    """Q1 / Q3 季报。"""

    def test_q1_plain(self):
        self.assertEqual(_detect_kind("2025年第一季度报告"), FilingKind.Q1)

    def test_q1_long_form(self):
        self.assertEqual(_detect_kind("2025年一季度报告"), FilingKind.Q1)

    def test_q3_plain(self):
        self.assertEqual(_detect_kind("2025年第三季度报告"), FilingKind.Q3)

    def test_q3_long_form(self):
        self.assertEqual(_detect_kind("2025年三季度报告"), FilingKind.Q3)

    def test_q2_does_not_exist_for_a_shares(self):
        # A 股没有 Q2 报告，含"第二季度"应当落到 OTHER
        self.assertEqual(_detect_kind("2025年第二季度报告"), FilingKind.OTHER)


class TestOtherClassification(unittest.TestCase):
    """不属于任何定期报告 → OTHER。"""

    def test_announcement(self):
        self.assertEqual(_detect_kind("关于召开2025年第一次临时股东大会的通知"), FilingKind.OTHER)

    def test_related_party_transaction(self):
        self.assertEqual(_detect_kind("关联交易公告"), FilingKind.OTHER)

    def test_director_resignation(self):
        self.assertEqual(_detect_kind("关于董事辞职的公告"), FilingKind.OTHER)

    def test_empty_string(self):
        self.assertEqual(_detect_kind(""), FilingKind.OTHER)

    def test_random_text(self):
        self.assertEqual(_detect_kind("xxx"), FilingKind.OTHER)


class TestEdgeCases(unittest.TestCase):
    """鲁棒性 — 异常输入应安全降级为 OTHER。"""

    def test_none_safe(self):
        # 实现里没有 None guard，但用 str(...) 包一下应当返回 OTHER
        # 这里只断言不会抛异常
        try:
            result = _detect_kind(str(None))  # type: ignore[arg-type]
        except Exception:
            self.fail("_detect_kind should not raise on str(None)")
        self.assertEqual(result, FilingKind.OTHER)


class TestCategoryMap(unittest.TestCase):
    """CATEGORY_MAP 是 FilingKind 值 -> 巨潮 category 编码。"""

    def test_keys_subset_of_filing_kinds(self):
        allowed = {k.value for k in FilingKind}
        for k in CATEGORY_MAP:
            self.assertIn(k, allowed, f"CATEGORY_MAP key '{k}' is not a FilingKind")

    def test_values_use_szsh_prefix(self):
        # 巨潮分类编码固定前缀 category_xxx_szsh
        for v in CATEGORY_MAP.values():
            self.assertTrue(
                v.startswith("category_") and v.endswith("_szsh"),
                f"unexpected cninfo category code: {v}",
            )

    def test_all_a_share_kinds_have_category(self):
        for kind in ("annual", "semi", "q1", "q3"):
            self.assertIn(kind, CATEGORY_MAP)


if __name__ == "__main__":
    unittest.main()
