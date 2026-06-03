"""Tests for HKEXStockRegistry."""
import json
import tempfile
import unittest
from unittest.mock import patch

import requests

from corp_finance_monitor.sources.hkex_registry import (
    HKEXStockRegistry,
    StockEntry,
    STOCK_LIST_URL,
)

SAMPLE_ACTIVE_STOCKS = [
    {"c": "00700", "i": 700, "e": "0700", "n": "TENCENT"},
    {"c": "09988", "i": 9988, "e": "9988", "n": "BABA-SW"},
    {"c": "00005", "i": 5, "e": "0005", "n": "HSBC HOLDINGS"},
    {"c": "", "i": 999, "e": "", "n": ""},
    {"c": "02388", "i": 2388, "e": "2388", "n": "BOC HONG KONG"},
]


class TestHKEXRegistry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _fresh_registry(self):
        r = HKEXStockRegistry(cache_dir=self.cache_dir, ttl_hours=24)
        r.initialize()
        return r

    def _mock_response(self, data, status=200):
        resp = requests.Response()
        resp.status_code = status
        resp._content = json.dumps(data).encode()
        return resp

    def test_initial_empty(self):
        r = self._fresh_registry()
        self.assertEqual(r.count(), 0)
        self.assertEqual(r.get_all(), [])
        self.assertIsNone(r.lookup("00700"))
        r.close()

    def test_refresh_populates_cache(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(SAMPLE_ACTIVE_STOCKS)
            count = r.refresh()

        self.assertEqual(count, 4)  # 5 entries, 1 empty code filtered out
        self.assertEqual(r.count(), 4)
        all_stocks = r.get_all()
        self.assertEqual(len(all_stocks), 4)
        self.assertEqual(all_stocks[0].stock_code, "00005")  # sorted by stock_code
        r.close()

    def test_refresh_network_failure_returns_zero(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.side_effect = ConnectionError("no network")
            count = r.refresh()

        self.assertEqual(count, 0)
        self.assertEqual(r.count(), 0)
        r.close()

    def test_refresh_empty_list(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response([])
            count = r.refresh()

        self.assertEqual(count, 0)
        r.close()

    def test_refresh_invalid_data(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response({"status": "error"})
            count = r.refresh()

        self.assertEqual(count, 0)
        r.close()

    def test_lookup(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(SAMPLE_ACTIVE_STOCKS)
            r.refresh()

        tencent = r.lookup("00700")
        self.assertIsNotNone(tencent)
        self.assertEqual(tencent.stock_code, "00700")
        self.assertEqual(tencent.name, "TENCENT")
        self.assertEqual(tencent.exchange, "SEHK")

        self.assertIsNone(r.lookup("99999"))
        r.close()

    def test_get_hk_stocks(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(SAMPLE_ACTIVE_STOCKS)
            r.refresh()

        hk = r.get_hk_stocks()
        self.assertEqual(len(hk), 4)
        r.close()

    def test_to_watchlist_entry(self):
        entry = StockEntry(stock_code="00700", name="TENCENT")
        wl = entry.to_watchlist_entry(kinds=["annual", "interim"])
        self.assertEqual(wl, {"stock": "00700", "kinds": ["annual", "interim"]})

        wl_no_kinds = entry.to_watchlist_entry()
        self.assertEqual(wl_no_kinds, {"stock": "00700"})

    def test_refresh_replaces_existing_data(self):
        r = self._fresh_registry()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(SAMPLE_ACTIVE_STOCKS)
            r.refresh()

        self.assertEqual(r.count(), 4)

        small = [{"c": "00700", "i": 700, "e": "0700", "n": "TENCENT"}]
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(small)
            r.refresh(force=True)

        self.assertEqual(r.count(), 1)
        r.close()

    def test_ttl_skips_fresh_cache(self):
        r = HKEXStockRegistry(cache_dir=self.cache_dir, ttl_hours=999)
        r.initialize()
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = self._mock_response(SAMPLE_ACTIVE_STOCKS)
            r.refresh()

        self.assertTrue(r.is_fresh())
        m.reset_mock()

        count = r.refresh()
        self.assertEqual(count, 4)
        m.assert_not_called()
        r.close()

    def test_close(self):
        r = self._fresh_registry()
        r.close()
        self.assertEqual(r.count(), 0)
        self.assertEqual(r.get_all(), [])

    def test_repr(self):
        entry = StockEntry(stock_code="00700", name="TENCENT")
        self.assertIn("00700", repr(entry))
        self.assertIn("TENCENT", repr(entry))
