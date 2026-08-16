"""Tests for CninfoStockRegistry — stock list fetching, caching, and queries."""

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from corp_finance_monitor.sources.stock_registry import (
    STOCK_LIST_URL,
    CninfoStockRegistry,
    StockEntry,
    _infer_exchange,
)


class TestInferExchange(unittest.TestCase):
    def test_szse_codes(self):
        self.assertEqual(_infer_exchange("000001"), "SZSE")
        self.assertEqual(_infer_exchange("000725"), "SZSE")
        self.assertEqual(_infer_exchange("002001"), "SZSE")
        self.assertEqual(_infer_exchange("300001"), "SZSE")

    def test_sse_codes(self):
        self.assertEqual(_infer_exchange("600000"), "SSE")
        self.assertEqual(_infer_exchange("601398"), "SSE")
        self.assertEqual(_infer_exchange("688981"), "SSE")

    def test_bse_codes(self):
        self.assertEqual(_infer_exchange("430001"), "BSE")
        self.assertEqual(_infer_exchange("830001"), "BSE")
        self.assertEqual(_infer_exchange("870001"), "BSE")
        self.assertEqual(_infer_exchange("920010"), "BSE")


SAMPLE_STOCK_LIST = {
    "stockList": [
        {
            "code": "000001",
            "orgId": "gssz0000001",
            "category": "A股",
            "pinyin": "payh",
            "zwjc": "平安银行",
        },
        {
            "code": "000725",
            "orgId": "gssz0000725",
            "category": "A股",
            "pinyin": "jda",
            "zwjc": "京东方A",
        },
        {
            "code": "600000",
            "orgId": "gssh0600000",
            "category": "A股",
            "pinyin": "pfyh",
            "zwjc": "浦发银行",
        },
        {
            "code": "688981",
            "orgId": "9900031171",
            "category": "A股",
            "pinyin": "zxxc",
            "zwjc": "中芯国际",
        },
        {
            "code": "430001",
            "orgId": "gfbj0028001",
            "category": "A股",
            "pinyin": "",
            "zwjc": "世纪瑞尔",
        },
        {
            "code": "920010",
            "orgId": "gfbj9200010",
            "category": "A股",
            "pinyin": "",
            "zwjc": "北交示例",
        },
        {
            "code": "200002",
            "orgId": "gssz0000002",
            "category": "B股",
            "pinyin": "wjb",
            "zwjc": "万科B",
        },
        {"code": "", "orgId": "gssz0000003", "category": "A股", "pinyin": "", "zwjc": "空代码"},
        {"code": "000010", "orgId": "", "category": "A股", "pinyin": "", "zwjc": "空orgId"},
    ]
}


class TestCninfoStockRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = CninfoStockRegistry(cache_dir=self.tmpdir, ttl_hours=24)
        self.registry.initialize()

    def tearDown(self):
        self.registry.close()

    def test_initial_empty(self):
        self.assertEqual(self.registry.count(), 0)
        self.assertFalse(self.registry.is_fresh())
        self.assertEqual(self.registry.get_all(), [])

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_refresh_populates_cache(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp

        count = self.registry.refresh(force=True)
        self.assertEqual(count, 7)
        mock_get.assert_called_once_with(STOCK_LIST_URL)

        self.assertEqual(self.registry.count(), 7)
        self.assertTrue(self.registry.is_fresh())

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_refresh_network_failure_returns_zero(self, mock_get):
        mock_get.side_effect = ConnectionError("network down")
        count = self.registry.refresh(force=True)
        self.assertEqual(count, 0)
        self.assertEqual(self.registry.count(), 0)

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_refresh_empty_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stockList": []}
        mock_get.return_value = mock_resp
        count = self.registry.refresh(force=True)
        self.assertEqual(count, 0)

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_get_all_and_filters(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        self.assertEqual(len(self.registry.get_all()), 7)

        szse = self.registry.get_all(exchange="SZSE")
        self.assertEqual(len(szse), 3)
        for entry in szse:
            self.assertEqual(entry.exchange, "SZSE")

        self.assertEqual(len(self.registry.get_all(exchange="SSE")), 2)
        self.assertEqual(len(self.registry.get_all(exchange="BSE")), 2)
        self.assertEqual(self.registry.count(exchange="BSE"), 2)

        self.assertEqual(len(self.registry.get_all(category="A股")), 6)
        self.assertEqual(len(self.registry.get_all(category="B股")), 1)

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_get_a_shares_includes_b_shares(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        # 境内权益覆盖：A股(6) + B股(1)，不再精确过滤 category='A股'
        entries = self.registry.get_a_shares()
        self.assertEqual(len(entries), 7)
        codes = {entry.stock_code for entry in entries}
        self.assertIn("200002", codes)
        self.assertTrue(
            all(entry.category in ("A股", "B股", "CDR") for entry in entries),
            [entry.category for entry in entries],
        )

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_get_all_categories_in_filter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        # categories IN 过滤：A股(6) + B股(1)
        entries = self.registry.get_all(categories=["A股", "B股"])
        self.assertEqual(len(entries), 7)
        # 单 category 过滤保持兼容
        self.assertEqual(len(self.registry.get_all(category="A股")), 6)

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_lookup(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        entry = self.registry.lookup("000725")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.org_id, "gssz0000725")
        self.assertEqual(entry.name, "京东方A")
        self.assertEqual(entry.exchange, "SZSE")
        self.assertIsNone(self.registry.lookup("999999"))

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_to_watchlist_entry(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        entry = self.registry.lookup("000725")
        self.assertEqual(
            entry.to_watchlist_entry(kinds=["annual", "semi"]),
            {"stock": "000725", "org_id": "gssz0000725", "kinds": ["annual", "semi"]},
        )
        self.assertEqual(
            entry.to_watchlist_entry(),
            {"stock": "000725", "org_id": "gssz0000725"},
        )

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_refresh_replaces_existing_data(self, mock_get):
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp1
        self.registry.refresh(force=True)
        self.assertEqual(self.registry.count(), 7)

        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {
            "stockList": [
                {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
            ]
        }
        mock_get.return_value = mock_resp2
        self.registry.refresh(force=True)
        self.assertEqual(self.registry.count(), 1)

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_ttl_skips_fresh_cache(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp

        self.registry.refresh(force=True)
        self.assertEqual(mock_get.call_count, 1)

        count = self.registry.refresh(force=False)
        self.assertEqual(count, 7)
        self.assertEqual(mock_get.call_count, 1)


# BSE 新旧码双码共享 orgId（920xxx 为旧 4/8 号段改码而来）+ CDR 覆盖
ALIAS_STOCK_LIST = {
    "stockList": [
        {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
        {"code": "920010", "orgId": "gfbj9200010", "category": "A股", "zwjc": "北交单码"},
        {"code": "833454", "orgId": "gfbj0833454", "category": "A股", "zwjc": "同心传动"},
        {"code": "920454", "orgId": "gfbj0833454", "category": "A股", "zwjc": "同心传动"},
        {"code": "832089", "orgId": "gfbj0832089", "category": "A股", "zwjc": "禾昌聚合"},
        {"code": "920089", "orgId": "gfbj0832089", "category": "A股", "zwjc": "禾昌聚合"},
        {"code": "689009", "orgId": "9900037993", "category": "CDR", "zwjc": "九号公司"},
    ]
}


class TestCodeAliases(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = CninfoStockRegistry(cache_dir=self.tmpdir, ttl_hours=24)
        self.registry.initialize()

    def tearDown(self):
        self.registry.close()

    def _refresh(self, payload) -> int:
        with patch("corp_finance_monitor.sources.stock_registry.http_get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = payload
            mock_get.return_value = mock_resp
            return self.registry.refresh(force=True)

    def test_get_a_shares_includes_cdr(self):
        self._refresh(ALIAS_STOCK_LIST)
        entries = self.registry.get_a_shares()
        self.assertEqual(len(entries), 7)
        codes = {entry.stock_code for entry in entries}
        self.assertIn("689009", codes)

    def test_alias_dual_code_group_symmetric(self):
        self._refresh(ALIAS_STOCK_LIST)
        # 同一 orgId 新旧双码互为 alias，双向一致
        self.assertEqual(self.registry.get_code_aliases("920454"), ["833454", "920454"])
        self.assertEqual(self.registry.get_code_aliases("833454"), ["833454", "920454"])
        self.assertEqual(self.registry.get_code_aliases("920089"), ["832089", "920089"])
        self.assertEqual(self.registry.get_code_aliases("832089"), ["832089", "920089"])

    def test_alias_single_and_unknown_code_returns_self(self):
        self._refresh(ALIAS_STOCK_LIST)
        # 无共享 orgId 的单码与未知代码都返回自身
        self.assertEqual(self.registry.get_code_aliases("000001"), ["000001"])
        self.assertEqual(self.registry.get_code_aliases("920010"), ["920010"])
        self.assertEqual(self.registry.get_code_aliases("999999"), ["999999"])

    def test_alias_sorted_and_deterministic(self):
        self._refresh(ALIAS_STOCK_LIST)
        first = self.registry.get_code_aliases("920454")
        second = self.registry.get_code_aliases("920454")
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first))

    def test_refresh_invalidates_alias_map(self):
        self._refresh(ALIAS_STOCK_LIST)
        self.assertEqual(self.registry.get_code_aliases("920454"), ["833454", "920454"])

        # 数据更新后双码解除共享（模拟 orgId 变更），alias map 必须重建
        self._refresh(
            {
                "stockList": [
                    {
                        "code": "833454",
                        "orgId": "gfbj0833454",
                        "category": "A股",
                        "zwjc": "同心传动",
                    },
                    {
                        "code": "920454",
                        "orgId": "gfbj9200454",
                        "category": "A股",
                        "zwjc": "新码独立",
                    },
                ]
            }
        )
        self.assertEqual(self.registry.get_code_aliases("920454"), ["920454"])
        self.assertEqual(self.registry.get_code_aliases("833454"), ["833454"])


class TestStockEntry(unittest.TestCase):
    def test_repr(self):
        entry = StockEntry("000725", "gssz0000725", "京东方A", "SZSE", "A股")
        rendered = repr(entry)
        self.assertIn("000725", rendered)
        self.assertIn("京东方A", rendered)


if __name__ == "__main__":
    unittest.main()
