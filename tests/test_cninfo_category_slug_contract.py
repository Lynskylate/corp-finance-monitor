"""
Contract test: pin the exact cninfo category slugs sent to the announcement API.

Why this exists: cninfo renames category slugs WITHOUT any error signal — a dead
slug is silently ignored (market-wide queries return unfiltered results; joined
queries just lose that category's filings). On 2026-08-16 the forecast slug
`category_yjyg_szsh` was found dead and renamed to `category_yjygjxz_szsh`,
which made every full-market scan silently miss all 业绩预告.

These tests intentionally pin literal values. If cninfo renames a slug again,
these assertions fail and force a deliberate update with evidence (probe the
API before changing), instead of a silent data gap.
"""

import unittest

from corp_finance_monitor.sources.cninfo import ALL_KINDS, CATEGORY_MAP
from tests.conftest import SRC  # noqa: F401  (forces src/ onto sys.path)

# Slugs verified live against https://www.cninfo.com.cn/new/hisAnnouncement/query
# on 2026-08-16 (probe evidence in #corp-finance-monitor thread 7a218fd2).
EXPECTED_CATEGORY_MAP = {
    "annual": "category_ndbg_szsh",
    "semi": "category_bndbg_szsh",
    "q1": "category_yjdbg_szsh",
    "q3": "category_sjdbg_szsh",
    "forecast": "category_yjygjxz_szsh",  # renamed from category_yjyg_szsh (dead)
    "prospectus": "category_zf_szsh",  # suspected dead 2026-08-16, unused in active kinds
}


class TestCategorySlugContract(unittest.TestCase):
    def test_category_map_pinned(self):
        self.assertEqual(CATEGORY_MAP, EXPECTED_CATEGORY_MAP)

    def test_all_kinds_pinned_and_consistent(self):
        self.assertEqual(
            ALL_KINDS,
            "category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh;"
            "category_sjdbg_szsh;category_yjygjxz_szsh;category_zf_szsh",
        )
        # every mapped slug must appear in ALL_KINDS (default scan covers all kinds)
        for slug in CATEGORY_MAP.values():
            self.assertIn(slug, ALL_KINDS)

    def test_no_dead_forecast_slug(self):
        # The exact dead slug that silently dropped all forecasts 2026-08-16.
        self.assertNotIn("category_yjyg_szsh", ALL_KINDS)
        self.assertNotIn("category_yjyg_szsh", CATEGORY_MAP.values())


if __name__ == "__main__":
    unittest.main()
