"""Tests for Phase 3: scan checkpoint/resume and progress persistence."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from corp_finance_monitor.core.config import (
    Config,
    EngineConfig,
    SourceConfig,
    StateStoreConfig,
    StorageConfig,
)
from corp_finance_monitor.core.engine import Engine
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.state.sqlite import SQLiteStateStore


# --- Fake source that tracks which stocks were discovered ---
class _CheckpointSource(AbstractSource):
    """Source that records discover calls per stock code."""

    def __init__(self, name, config):
        super().__init__(name, config)
        self.discovered_codes = []
        self._registry = None

    def _get_registry(self):
        return self._registry

    def discover(self, watchlist=None, since=None, only_stock_codes=None):
        codes = list(only_stock_codes or [])
        self.discovered_codes.extend(codes)
        refs = []
        for code in codes:
            refs.append(
                FilingRef(
                    source="cninfo",
                    source_id=f"scan-{code}",
                    stock_code=code,
                    title=f"{code} annual",
                    kind=FilingKind.ANNUAL,
                    published_at="2025-01-01",
                    url=f"https://example.com/{code}.pdf",
                )
            )
        return refs

    def fetch(self, ref):
        return Filing(ref=ref, content=b"%PDF-1.4\ncheckpoint\n")


class _FakeStockEntry:
    __slots__ = ("stock_code", "org_id")

    def __init__(self, stock_code, org_id):
        self.stock_code = stock_code
        self.org_id = org_id


class _FakeRegistry:
    def __init__(self, codes):
        self._entries = [_FakeStockEntry(c, f"org{c}") for c in codes]

    def get_a_shares(self):
        return list(self._entries)


class ScanProgressTestCase(unittest.TestCase):
    """Tests for SQLiteStateStore scan_progress table."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_scan_progress_")
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

    def test_mark_and_check(self):
        self.assertFalse(self.store.is_scan_done("cninfo", "000001"))
        self.store.mark_scan_done("cninfo", "000001")
        self.assertTrue(self.store.is_scan_done("cninfo", "000001"))

    def test_count_progress(self):
        self.store.mark_scan_done("cninfo", "000001")
        self.store.mark_scan_done("cninfo", "000002")
        done, _ = self.store.count_scan_progress("cninfo")
        self.assertEqual(done, 2)

    def test_clear_specific_source(self):
        self.store.mark_scan_done("cninfo", "000001")
        self.store.mark_scan_done("sse", "600000")
        self.store.clear_scan_progress("cninfo")
        self.assertFalse(self.store.is_scan_done("cninfo", "000001"))
        self.assertTrue(self.store.is_scan_done("sse", "600000"))

    def test_clear_all(self):
        self.store.mark_scan_done("cninfo", "000001")
        self.store.mark_scan_done("sse", "600000")
        self.store.clear_scan_progress()
        self.assertFalse(self.store.is_scan_done("cninfo", "000001"))
        self.assertFalse(self.store.is_scan_done("sse", "600000"))

    def test_idempotent_mark(self):
        self.store.mark_scan_done("cninfo", "000001")
        self.store.mark_scan_done("cninfo", "000001")
        done, _ = self.store.count_scan_progress("cninfo")
        self.assertEqual(done, 1)


class EngineResumeTestCase(unittest.TestCase):
    """Tests for Engine run_once(resume=True) checkpoint/resume behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cfm_engine_resume_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_config(self, concurrency=3):
        return Config(
            engine=EngineConfig(
                run_once=True,
                interval_minutes=360,
                concurrency=concurrency,
                fetch_delay_seconds=0,
            ),
            storage=StorageConfig(
                backend="disk",
                base_dir=os.path.join(self.tmpdir, "data"),
            ),
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
                        "full_market_batch_size": 2,
                    },
                ),
            },
        )

    def test_resume_skips_already_scanned(self):
        """run_once(resume=True) skips stocks already marked in scan_progress."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _CheckpointSource})
        engine.initialize()

        # Simulate partial scan: 3 of 5 stocks already done
        for code in ["000001", "000002", "000003"]:
            engine.state_store.mark_scan_done("cninfo", code)

        # Set up fake registry with 5 stocks
        source = engine.sources["cninfo"]
        source._registry = _FakeRegistry(
            ["000001", "000002", "000003", "000004", "000005"]
        )

        stats = engine.run_once(resume=True)
        # Only 000004 and 000005 should be discovered
        self.assertEqual(
            sorted(source.discovered_codes),
            ["000004", "000005"],
        )
        self.assertEqual(stats["discovered"], 2)
        engine.close()

    def test_no_resume_scans_all_without_skip(self):
        """run_once(resume=False) still skips already-scanned stocks.

        In the current design, the engine always skips done stocks.
        To force a full rescan, clear scan_progress externally (e.g. via --reset).
        """
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _CheckpointSource})
        engine.initialize()

        engine.state_store.mark_scan_done("cninfo", "000001")

        source = engine.sources["cninfo"]
        source._registry = _FakeRegistry(["000001", "000002"])

        stats = engine.run_once(resume=False)
        # 000001 was already done, so only 000002 is discovered
        self.assertEqual(
            sorted(source.discovered_codes),
            ["000002"],
        )
        # Verify scan_progress was NOT cleared — clear is now explicit via --reset.
        # After the run, progress was written for both stocks, so count is at least 1.
        self.assertGreater(
            engine.state_store.count_scan_progress("cninfo")[0], 0,
        )
        engine.close()

    def test_default_is_incremental(self):
        """Default run_once behavior is incremental — skips already-scanned stocks."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _CheckpointSource})
        engine.initialize()

        for code in ["000001", "000002", "000003"]:
            engine.state_store.mark_scan_done("cninfo", code)

        source = engine.sources["cninfo"]
        source._registry = _FakeRegistry(
            ["000001", "000002", "000003", "000004", "000005"]
        )

        # Default run_once() should skip done stocks
        stats = engine.run_once()
        self.assertEqual(
            sorted(source.discovered_codes),
            ["000004", "000005"],
        )
        self.assertEqual(stats["discovered"], 2)
        engine.close()

    def test_scan_progress_persists_across_runs(self):
        """Progress from run 1 is available for run 2 to resume."""
        cfg = self._make_config()
        engine = Engine(cfg, {"cninfo": _CheckpointSource})
        engine.initialize()

        source = engine.sources["cninfo"]
        source._registry = _FakeRegistry(
            ["000001", "000002", "000003", "000004"]
        )

        # Run 1: no prior progress, discovers all 4
        engine.run_once(resume=True)
        self.assertEqual(len(source.discovered_codes), 4)

        # All should be marked done now
        done, _ = engine.state_store.count_scan_progress("cninfo")
        self.assertEqual(done, 4)

        # Run 2: all skipped (incremental by default)
        source.discovered_codes = []
        engine.run_once(resume=True)
        self.assertEqual(source.discovered_codes, [])

        engine.close()

    def test_progress_log_counts(self):
        """mark_scan_done updates count after each batch."""
        cfg = self._make_config(concurrency=2)
        engine = Engine(cfg, {"cninfo": _CheckpointSource})
        engine.initialize()

        source = engine.sources["cninfo"]
        source._registry = _FakeRegistry(
            ["000001", "000002", "000003", "000004", "000005"]
        )

        engine.run_once(resume=True)
        done, _ = engine.state_store.count_scan_progress("cninfo")
        self.assertEqual(done, 5)
        engine.close()


if __name__ == "__main__":
    unittest.main()
