"""Tests for HKEXSource full_market mode."""

import json
import tempfile
import unittest
from unittest.mock import patch

import requests

from corp_finance_monitor.core.config import SourceConfig
from corp_finance_monitor.core.model import FilingKind
from corp_finance_monitor.sources.hkex import HKEXSource


def _make_source(options=None, watchlist=None):
    options = dict(options or {})
    options.setdefault("full_market", True)
    cfg = SourceConfig(
        name="hkex",
        options=options,
        watchlist=watchlist or [],
    )
    return HKEXSource(name="hkex", config=cfg)


def _mock_response(data, status=200):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
    return resp


SAMPLE_STOCKS = [
    {"c": "00700", "i": 700, "e": "0700", "n": "TENCENT"},
    {"c": "09988", "i": 9988, "e": "9988", "n": "BABA-SW"},
    {"c": "00005", "i": 5, "e": "0005", "n": "HSBC HOLDINGS"},
]

SINGLE_STOCK = [{"c": "00700", "i": 700, "e": "0700", "n": "TENCENT"}]


def _hkex_search_response(news_id="12345", title="Annual Report 2024", date="15/03/2025"):
    return {
        "result": json.dumps(
            [
                {
                    "NEWS_ID": news_id,
                    "TITLE": title,
                    "FILE_LINK": "/final/2025/http://example.com/file.pdf",
                    "DATE_TIME": f"{date} 16:30",
                    "STOCK_NAME": "TENCENT",
                }
            ]
        ),
    }


class TestHKEXSourceFullMarket(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_market_uses_registry(self):
        source = _make_source(
            options={
                "full_market": True,
                "registry_cache_dir": self.cache_dir,
                "kinds": ["annual"],
            }
        )

        with (
            patch("corp_finance_monitor.sources.hkex_registry.http_get") as m_reg,
            patch("corp_finance_monitor.sources.hkex.http_get") as m_hkex,
        ):
            # First call: _fetch_stock_id fetches from stock list URL
            # Second call: search API
            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    return _mock_response(SINGLE_STOCK)
                return _mock_response(_hkex_search_response())

            m_reg.return_value = _mock_response(SINGLE_STOCK)
            m_hkex.side_effect = hkex_get

            refs = source.discover()

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source, "hkex")
        self.assertEqual(refs[0].stock_code, "00700")
        self.assertEqual(refs[0].kind, FilingKind.ANNUAL)
        source.close()

    def test_full_market_limit(self):
        source = _make_source(
            options={
                "full_market": True,
                "full_market_limit": 1,
                "registry_cache_dir": self.cache_dir,
                "kinds": ["annual"],
            }
        )

        with (
            patch("corp_finance_monitor.sources.hkex_registry.http_get") as m_reg,
            patch("corp_finance_monitor.sources.hkex.http_get") as m_hkex,
        ):
            m_reg.return_value = _mock_response(SAMPLE_STOCKS)

            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    return _mock_response(SAMPLE_STOCKS)
                return _mock_response(_hkex_search_response())

            m_hkex.side_effect = hkex_get

            refs = source.discover()

        self.assertEqual(len(refs), 1)
        source.close()

    def test_full_market_only_stock_codes(self):
        source = _make_source(
            options={
                "full_market": True,
                "registry_cache_dir": self.cache_dir,
                "kinds": ["annual"],
            }
        )

        with (
            patch("corp_finance_monitor.sources.hkex_registry.http_get") as m_reg,
            patch("corp_finance_monitor.sources.hkex.http_get") as m_hkex,
        ):
            m_reg.return_value = _mock_response(SAMPLE_STOCKS)

            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    code = "00005"
                    return _mock_response([{"c": code, "i": 5, "e": "0005", "n": "HSBC"}])
                return _mock_response(_hkex_search_response())

            m_hkex.side_effect = hkex_get

            refs = source.discover(only_stock_codes=["00005"])

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "00005")
        source.close()

    def test_full_market_registry_failure_no_crash(self):
        source = _make_source(
            options={
                "full_market": True,
                "registry_cache_dir": self.cache_dir,
            }
        )

        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.side_effect = ConnectionError("no network")
            refs = source.discover()

        self.assertEqual(refs, [])
        source.close()

    def test_watchlist_mode_ignored_in_full_market(self):
        source = _make_source(
            options={
                "full_market": True,
                "registry_cache_dir": self.cache_dir,
                "kinds": ["annual"],
            },
            watchlist=[{"stock": "00001", "kinds": ["annual"]}],
        )

        with (
            patch("corp_finance_monitor.sources.hkex_registry.http_get") as m_reg,
            patch("corp_finance_monitor.sources.hkex.http_get") as m_hkex,
        ):
            m_reg.return_value = _mock_response([{"c": "00005", "i": 5, "e": "0005", "n": "HSBC"}])

            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    return _mock_response([{"c": "00005", "i": 5, "e": "0005", "n": "HSBC"}])
                return _mock_response(_hkex_search_response())

            m_hkex.side_effect = hkex_get

            refs = source.discover()

        # Should use registry (00005) not watchlist (00001)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "00005")
        source.close()

    def test_close_without_registry(self):
        source = _make_source(options={"full_market": False})
        source.close()
        self.assertIsNone(source._registry)

    def test_close_cleans_up_registry(self):
        source = _make_source(
            options={
                "full_market": True,
                "registry_cache_dir": self.cache_dir,
            }
        )
        with patch("corp_finance_monitor.sources.hkex_registry.http_get") as m:
            m.return_value = _mock_response(SAMPLE_STOCKS)
            source.discover()

        self.assertIsNotNone(source._registry)
        source.close()
        self.assertIsNone(source._registry)

    def test_watchlist_mode_still_works(self):
        source = _make_source(
            options={"full_market": False},
            watchlist=[{"stock": "00700", "kinds": ["annual"]}],
        )

        with patch("corp_finance_monitor.sources.hkex.http_get") as m:

            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    return _mock_response(SINGLE_STOCK)
                return _mock_response(_hkex_search_response())

            m.side_effect = hkex_get
            refs = source.discover()

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "00700")
        self.assertEqual(refs[0].kind, FilingKind.ANNUAL)
        source.close()

    def test_watchlist_uses_override_param(self):
        source = _make_source(
            options={"full_market": False},
            watchlist=[{"stock": "00001", "kinds": ["annual"]}],
        )

        with patch("corp_finance_monitor.sources.hkex.http_get") as m:

            def hkex_get(url, **kwargs):
                if "activestock" in url:
                    return _mock_response([{"c": "00700", "i": 700, "e": "0700", "n": "TENCENT"}])
                return _mock_response(_hkex_search_response())

            m.side_effect = hkex_get
            refs = source.discover(watchlist=[{"stock": "00700", "kinds": ["annual"]}])

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "00700")
        source.close()
