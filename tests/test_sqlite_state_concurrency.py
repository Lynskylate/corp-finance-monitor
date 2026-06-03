"""
Concurrency tests for SQLiteStateStore.

Targets:
- has_filing / record_filing from multiple threads do not deadlock
  and do not lose data.
- record_run from many threads produces monotonic IDs and never raises.
- create_subscription is safe under concurrent writers.
- last_successful_run_start returns the most recent run with fetched > 0.

The store is used in production with `check_same_thread=False` and an
RLock guarding every SQL call, so we verify the safety contract
empirically rather than rely on a theoretical guarantee.
"""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from corp_finance_monitor.core.config import StateStoreConfig
from corp_finance_monitor.core.model import FilingKind, FilingRef, Subscription
from corp_finance_monitor.state.sqlite import SQLiteStateStore
from tests.conftest import SRC  # noqa: F401


def _ref(i: int) -> FilingRef:
    return FilingRef(
        source="cninfo",
        source_id=str(i),
        stock_code="000725",
        stock_name="BOE",
        title=f"filing-{i}",
        kind=FilingKind.ANNUAL,
        published_at="2025-04-01",
        url=f"https://example.com/{i}.pdf",
    )


class _StateStoreTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = self._tmpdir()
        self.cfg = StateStoreConfig(
            backend="sqlite",
            path=os.path.join(self.tmp, "state.db"),
        )
        self.store = SQLiteStateStore(self.cfg)
        self.store.initialize()

    def tearDown(self):
        self.store.close()
        import shutil

        if os.path.isdir(self.tmp):
            shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _tmpdir() -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="cfm_state_test_")


class TestBasicOperations(_StateStoreTestBase):
    def test_initialize_creates_tables(self):
        # Should not raise
        cur = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {row[0] for row in cur.fetchall()}
        self.assertIn("filing_state", names)
        self.assertIn("run_log", names)
        self.assertIn("subscriptions", names)

    def test_record_and_lookup_filing(self):
        ref = _ref(1)
        self.assertFalse(self.store.has_filing(ref))
        self.store.record_filing(ref, "/tmp/x.pdf")
        self.assertTrue(self.store.has_filing(ref))

    def test_record_run_returns_id_and_persists(self):
        rid = self.store.record_run(
            "2025-06-01T00:00:00",
            "2025-06-01T00:01:00",
            discovered=5,
            fetched=4,
            failed=1,
        )
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)
        runs = self.store.list_runs(limit=10)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].id, rid)
        self.assertEqual(runs[0].fetched, 4)

    def test_last_successful_run_picks_fetched_positive(self):
        # failed-only run should be ignored
        self.store.record_run("2025-01-01T00:00:00", "2025-01-01T00:01:00", 1, 0, 1)
        # successful run
        rid = self.store.record_run("2025-02-01T00:00:00", "2025-02-01T00:01:00", 3, 2, 0)
        last = self.store.last_successful_run_start()
        self.assertEqual(last, "2025-02-01T00:00:00")
        self.assertIsNotNone(rid)

    def test_last_successful_run_empty(self):
        self.assertIsNone(self.store.last_successful_run_start())

    def test_subscription_crud(self):
        sub = Subscription(
            id=None,
            name="boe-annual",
            source="cninfo",
            stock_code="000725",
            kind="annual",
            target="https://example.com/wh",
            active=True,
        )
        created = self.store.create_subscription(sub)
        self.assertIsNotNone(created.id)
        self.assertTrue(created.active)

        subs = self.store.list_subscriptions(active_only=True)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].name, "boe-annual")

        subs_inactive = self.store.list_subscriptions(active_only=False)
        self.assertEqual(len(subs_inactive), 1)


class TestConcurrentFilings(_StateStoreTestBase):
    """Many threads write / read the same set of unique keys."""

    def test_concurrent_record_filing_same_key(self):
        N_THREADS = 16
        N_PER_THREAD = 25
        ref = _ref(42)
        errors: list = []

        def worker(i: int):
            try:
                self.store.record_filing(ref, f"/tmp/x_{i}.pdf")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
            futures = [pool.submit(worker, i) for i in range(N_THREADS * N_PER_THREAD)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(errors, [], f"concurrent writes raised: {errors[:3]}")
        # Exactly one row in filing_state for this key
        cur = self.store._conn.execute(
            "SELECT COUNT(*) FROM filing_state WHERE unique_key = ?",
            (ref.unique_key,),
        )
        self.assertEqual(cur.fetchone()[0], 1)

    def test_concurrent_distinct_keys(self):
        N_THREADS = 16
        N_PER_THREAD = 20
        errors: list = []

        def worker(i: int):
            try:
                self.store.record_filing(_ref(i), f"/tmp/x_{i}.pdf")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
            futures = [pool.submit(worker, i) for i in range(N_THREADS * N_PER_THREAD)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(errors, [], f"concurrent writes raised: {errors[:3]}")
        cur = self.store._conn.execute("SELECT COUNT(*) FROM filing_state")
        self.assertEqual(cur.fetchone()[0], N_THREADS * N_PER_THREAD)

    def test_concurrent_has_filing_after_writes(self):
        ref = _ref(99)
        self.store.record_filing(ref, "/tmp/x.pdf")

        N = 32
        stop = threading.Event()
        errors: list = []

        def reader(_i: int):
            try:
                while not stop.is_set():
                    self.assertTrue(self.store.has_filing(ref))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()

        # Concurrent updaters
        def updater(i: int):
            try:
                for j in range(50):
                    self.store.record_filing(ref, f"/tmp/y_{i}_{j}.pdf")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with ThreadPoolExecutor(max_workers=4) as pool:
            for fut in as_completed([pool.submit(updater, i) for i in range(4)]):
                fut.result()

        stop.set()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(errors, [])


class TestConcurrentRuns(_StateStoreTestBase):
    def test_concurrent_record_runs_no_deadlock(self):
        N_THREADS = 8
        N_PER_THREAD = 25
        errors: list = []

        def worker(i: int):
            try:
                self.store.record_run(
                    f"2025-06-01T00:00:{i:02d}",
                    f"2025-06-01T00:01:{i:02d}",
                    discovered=10,
                    fetched=5,
                    failed=2,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
            futures = [pool.submit(worker, i) for i in range(N_THREADS * N_PER_THREAD)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(errors, [], f"concurrent runs raised: {errors[:3]}")
        cur = self.store._conn.execute("SELECT COUNT(*) FROM run_log")
        self.assertEqual(cur.fetchone()[0], N_THREADS * N_PER_THREAD)

    def test_list_runs_ordered_desc(self):
        for i in range(5):
            self.store.record_run(
                f"2025-06-0{i + 1}T00:00:00",
                f"2025-06-0{i + 1}T00:01:00",
                discovered=1,
                fetched=1,
                failed=0,
            )
        runs = self.store.list_runs(limit=10)
        self.assertEqual(len(runs), 5)
        # Monotonically decreasing id
        ids = [r.id for r in runs]
        self.assertEqual(ids, sorted(ids, reverse=True))


class TestConcurrentSubscriptions(_StateStoreTestBase):
    def test_concurrent_create_subscription(self):
        N = 16
        errors: list = []
        ids: list = []
        lock = threading.Lock()

        def worker(i: int):
            try:
                sub = Subscription(
                    id=None,
                    name=f"sub-{i}",
                    source="cninfo",
                    stock_code="000725",
                    kind="annual",
                    target="https://example.com/wh",
                    active=True,
                )
                created = self.store.create_subscription(sub)
                with lock:
                    ids.append(created.id)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for f in as_completed([pool.submit(worker, i) for i in range(N)]):
                f.result()

        self.assertEqual(errors, [], f"concurrent sub creates raised: {errors[:3]}")
        # All IDs unique
        self.assertEqual(len(set(ids)), N)
        # All persisted
        subs = self.store.list_subscriptions(active_only=False)
        self.assertEqual(len(subs), N)


if __name__ == "__main__":
    unittest.main()
