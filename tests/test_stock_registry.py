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
    def test_get_a_shares_convenience(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_STOCK_LIST
        mock_get.return_value = mock_resp
        self.registry.refresh(force=True)

        entries = self.registry.get_a_shares()
        self.assertEqual(len(entries), 6)
        for entry in entries:
            self.assertEqual(entry.category, "A股")

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


class TestStockEntry(unittest.TestCase):
    def test_repr(self):
        entry = StockEntry("000725", "gssz0000725", "京东方A", "SZSE", "A股")
        rendered = repr(entry)
        self.assertIn("000725", rendered)
        self.assertIn("京东方A", rendered)


if __name__ == "__main__":
    unittest.main()
