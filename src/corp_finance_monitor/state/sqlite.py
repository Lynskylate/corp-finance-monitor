from __future__ import annotations
import os
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from corp_finance_monitor.core.config import StateStoreConfig
from corp_finance_monitor.core.model import FilingRef, RunRecord, Subscription
from corp_finance_monitor.core.state import AbstractStateStore


class SQLiteStateStore(AbstractStateStore):
    def __init__(self, config: StateStoreConfig):
        self.path = os.path.abspath(config.path or "./data/.cfm_state/state.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def initialize(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS filing_state (
                    unique_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    stock_code TEXT,
                    title TEXT,
                    kind TEXT,
                    published_at TEXT,
                    fetched_at TEXT,
                    stored_path TEXT,
                    url TEXT DEFAULT ''
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT,
                    finished_at TEXT,
                    discovered INTEGER,
                    fetched INTEGER,
                    failed INTEGER
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT,
                    stock_code TEXT,
                    kind TEXT,
                    target TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_filing_state_source ON filing_state(source)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_filing_state_stock ON filing_state(stock_code)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_subscriptions_source ON subscriptions(source)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_progress (
                    source TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'done',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source, stock_code)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scan_progress_source ON scan_progress(source)"
            )
            self._conn.commit()

    def has_filing(self, ref: FilingRef) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM filing_state WHERE unique_key = ?",
                (ref.unique_key,),
            ).fetchone()
        return bool(row)

    def record_filing(self, ref: FilingRef, stored_path: str):
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO filing_state
                (unique_key, source, source_id, stock_code, title, kind, published_at, fetched_at, stored_path, url)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ref.unique_key,
                    ref.source,
                    ref.source_id,
                    ref.stock_code,
                    ref.title,
                    ref.kind.value,
                    ref.published_at,
                    datetime.utcnow().isoformat(),
                    stored_path,
                    ref.url,
                ),
            )
            self._conn.commit()

    def record_run(
        self,
        started_at: str,
        finished_at: str,
        discovered: int,
        fetched: int,
        failed: int,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO run_log (started_at, finished_at, discovered, fetched, failed)
                VALUES (?,?,?,?,?)
                """,
                (started_at, finished_at, discovered, fetched, failed),
            )
            self._conn.commit()
        return int(cur.lastrowid)

    def list_runs(self, limit: int = 20) -> List[RunRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, started_at, finished_at, discovered, fetched, failed
                FROM run_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            RunRecord(
                id=row["id"],
                started_at=row["started_at"] or "",
                finished_at=row["finished_at"] or "",
                discovered=row["discovered"] or 0,
                fetched=row["fetched"] or 0,
                failed=row["failed"] or 0,
            )
            for row in rows
        ]

    def last_successful_run_start(self) -> Optional[str]:
        """Return the started_at of the most recent run with no failures."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT started_at FROM run_log
                WHERE failed = 0
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return row["started_at"] if row else None

    def create_subscription(self, subscription: Subscription) -> Subscription:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO subscriptions (name, source, stock_code, kind, target, active)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    subscription.name,
                    subscription.source,
                    subscription.stock_code,
                    subscription.kind,
                    subscription.target,
                    1 if subscription.active else 0,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                """
                SELECT id, name, source, stock_code, kind, target, active, created_at, updated_at
                FROM subscriptions WHERE id = ?
                """,
                (cur.lastrowid,),
            ).fetchone()
        return self._row_to_subscription(row)

    def list_subscriptions(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Subscription]:
        query = """
            SELECT id, name, source, stock_code, kind, target, active, created_at, updated_at
            FROM subscriptions
            WHERE 1=1
        """
        params = []
        if source:
            query += " AND source = ?"
            params.append(source)
        if stock_code:
            query += " AND stock_code = ?"
            params.append(stock_code)
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY id DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_subscription(row) for row in rows]

    def delete_subscription(self, subscription_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM subscriptions WHERE id = ?", (subscription_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def mark_scan_done(self, source: str, stock_code: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO scan_progress (source, stock_code, status, updated_at)
                VALUES (?, ?, 'done', ?)
                """,
                (source, stock_code, now),
            )
            self._conn.commit()

    def is_scan_done(self, source: str, stock_code: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM scan_progress WHERE source = ? AND stock_code = ?",
                (source, stock_code),
            ).fetchone()
        return bool(row)

    def count_scan_progress(self, source: str) -> tuple[int, int]:
        """Return (done_count, total_count) for a source's current scan."""
        with self._lock:
            done_row = self._conn.execute(
                "SELECT COUNT(*) FROM scan_progress WHERE source = ?",
                (source,),
            ).fetchone()
        done_count = int(done_row[0]) if done_row else 0
        return done_count, 0  # total is tracked by engine, not stored here

    def clear_scan_progress(self, source: Optional[str] = None) -> None:
        with self._lock:
            if source:
                self._conn.execute(
                    "DELETE FROM scan_progress WHERE source = ?",
                    (source,),
                )
            else:
                self._conn.execute("DELETE FROM scan_progress")
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_subscription(row: sqlite3.Row) -> Subscription:
        return Subscription(
            id=row["id"],
            name=row["name"] or "",
            source=row["source"] or "",
            stock_code=row["stock_code"] or "",
            kind=row["kind"] or "",
            target=row["target"] or "",
            active=bool(row["active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
