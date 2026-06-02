"""Tests for CninfoSource full_market mode."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from corp_finance_monitor.core.config import SourceConfig
from corp_finance_monitor.core.model import FilingRef, FilingKind
from corp_finance_monitor.sources.cninfo import CninfoSource, API_URL


def _make_source(options=None, watchlist=None):
    """Helper to create a CninfoSource with given options/watchlist."""
    cfg = SourceConfig(
        name="cninfo",
        enabled=True,
        options=options or {},
        watchlist=watchlist or [],
    )
    return CninfoSource("cninfo", cfg)


# --- Minimal cninfo API response that discover() can parse ---
def _cninfo_response(announcements=None, has_more=False):
    """Build a fake cninfo API response."""
    if announcements is None:
        announcements = [
            {
                "announcementId": "123456",
                "announcementTitle": "2025年年度报告",
                "adjunctUrl": "2025/01/01/abc.pdf",
                "announcementTime": 1735689600000,
                "secName": "测试公司",
            },
        ]
    return {
        "announcements": announcements,
        "hasMore": has_more,
    }


class TestCninfoSourceWatchlistMode(unittest.TestCase):
    """Verify existing watchlist mode still works after refactor."""

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    def test_watchlist_mode_uses_config_watchlist(self, mock_post):
        """Without full_market, discover uses the config watchlist."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_resp

        source = _make_source(
            watchlist=[{"stock": "000725", "org_id": "gssz0000725"}],
        )
        refs = source.discover()

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "000725")
        mock_post.assert_called_once()

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    def test_watchlist_mode_uses_override_watchlist(self, mock_post):
        """Without full_market, explicit watchlist param takes priority."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_resp

        source = _make_source(
            watchlist=[{"stock": "000725", "org_id": "gssz0000725"}],
        )
        override = [{"stock": "000636", "org_id": "gssz0000636"}]
        refs = source.discover(watchlist=override)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].stock_code, "000636")

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    def test_empty_watchlist_returns_empty(self, mock_post):
        """Empty watchlist produces no refs."""
        source = _make_source(watchlist=[])
        refs = source.discover()
        self.assertEqual(refs, [])
        mock_post.assert_not_called()


class TestCninfoSourceFullMarketMode(unittest.TestCase):
    """Tests for full_market=True using CninfoStockRegistry."""

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_full_market_uses_registry(self, mock_registry_get, mock_post):
        """full_market mode fetches A-shares from registry and discovers."""
        # Registry mock: return 3 A-share stocks
        mock_reg_resp = MagicMock()
        mock_reg_resp.json.return_value = {
            "stockList": [
                {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
                {"code": "000725", "orgId": "gssz0000725", "category": "A股", "zwjc": "京东方A"},
                {"code": "600000", "orgId": "gssh0600000", "category": "A股", "zwjc": "浦发银行"},
            ]
        }
        mock_registry_get.return_value = mock_reg_resp

        # cninfo API mock: each stock gets one filing
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_post_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={"full_market": True, "registry_cache_dir": tmpdir},
                watchlist=[],  # watchlist should be ignored in full_market mode
            )
            refs = source.discover()

            self.assertEqual(len(refs), 3)
            stock_codes = {r.stock_code for r in refs}
            self.assertEqual(stock_codes, {"000001", "000725", "600000"})
            source.close()

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_full_market_limit(self, mock_registry_get, mock_post):
        """full_market_limit caps the number of stocks scanned."""
        # Registry mock: 5 stocks
        mock_reg_resp = MagicMock()
        mock_reg_resp.json.return_value = {
            "stockList": [
                {"code": f"00000{i}", "orgId": f"gssz000000{i}", "category": "A股", "zwjc": f"Stock{i}"}
                for i in range(1, 6)
            ]
        }
        mock_registry_get.return_value = mock_reg_resp

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_post_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={
                    "full_market": True,
                    "full_market_limit": 2,
                    "registry_cache_dir": tmpdir,
                },
            )
            refs = source.discover()

            self.assertEqual(len(refs), 2)
            stock_codes = [r.stock_code for r in refs]
            self.assertEqual(stock_codes, ["000001", "000002"])
            source.close()

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_full_market_ignores_config_watchlist(self, mock_registry_get, mock_post):
        """full_market mode ignores the watchlist parameter entirely."""
        mock_reg_resp = MagicMock()
        mock_reg_resp.json.return_value = {
            "stockList": [
                {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
            ]
        }
        mock_registry_get.return_value = mock_reg_resp

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_post_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={"full_market": True, "registry_cache_dir": tmpdir},
                # This watchlist should be ignored
                watchlist=[{"stock": "999999", "org_id": "fake"}],
            )
            # Pass explicit watchlist override — should also be ignored
            refs = source.discover(
                watchlist=[{"stock": "888888", "org_id": "also_fake"}],
            )

            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].stock_code, "000001")
            source.close()

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_full_market_registry_failure_no_crash(self, mock_registry_get):
        """If registry refresh fails, discover returns empty (no crash)."""
        mock_registry_get.side_effect = ConnectionError("network down")

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={"full_market": True, "registry_cache_dir": tmpdir},
            )
            refs = source.discover()
            self.assertEqual(refs, [])
            source.close()

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_full_market_excludes_non_a_shares(self, mock_registry_get, mock_post):
        """full_market only scans A-shares, not B-shares."""
        mock_reg_resp = MagicMock()
        mock_reg_resp.json.return_value = {
            "stockList": [
                {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
                {"code": "200002", "orgId": "gssz0000002", "category": "B股", "zwjc": "万科B"},
            ]
        }
        mock_registry_get.return_value = mock_reg_resp

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_post_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={"full_market": True, "registry_cache_dir": tmpdir},
            )
            refs = source.discover()

            # Only the A-share stock should produce a ref
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].stock_code, "000001")
            source.close()


class TestCninfoSourceClose(unittest.TestCase):
    """Verify close() cleans up registry resources."""

    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_close_without_registry(self, mock_get):
        """close() is safe even when registry was never initialised."""
        source = _make_source(options={"full_market": True})
        source.close()  # should not raise

    @patch("corp_finance_monitor.sources.cninfo.http_post")
    @patch("corp_finance_monitor.sources.stock_registry.http_get")
    def test_close_cleans_up_registry(self, mock_registry_get, mock_post):
        """After close(), internal registry reference is cleared."""
        mock_reg_resp = MagicMock()
        mock_reg_resp.json.return_value = {
            "stockList": [
                {"code": "000001", "orgId": "gssz0000001", "category": "A股", "zwjc": "平安银行"},
            ]
        }
        mock_registry_get.return_value = mock_reg_resp
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = _cninfo_response()
        mock_post.return_value = mock_post_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            source = _make_source(
                options={"full_market": True, "registry_cache_dir": tmpdir},
            )
            source.discover()
            self.assertIsNotNone(source._registry)

            source.close()
            self.assertIsNone(source._registry)


if __name__ == "__main__":
    unittest.main()
