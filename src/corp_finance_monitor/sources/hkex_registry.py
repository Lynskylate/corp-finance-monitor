"""
HKEX Stock Registry — 自动获取并缓存港股全量股票列表。

数据源: https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json
该接口一次返回全量 SEHK 主板股票列表（约 2500 条），无需分页。

本地缓存: data/.cfm_state/hkex_stocks.db (SQLite)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .base import http_get

logger = logging.getLogger("cfm.hkex_registry")

STOCK_LIST_URL = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json"


class StockEntry:
    """单只股票的注册信息。"""

    __slots__ = ("stock_code", "name", "exchange")

    def __init__(
        self,
        stock_code: str,
        name: str = "",
        exchange: str = "SEHK",
    ):
        self.stock_code = stock_code
        self.name = name
        self.exchange = exchange

    def to_watchlist_entry(self, kinds: list[str] | None = None) -> dict:
        entry: dict = {"stock": self.stock_code}
        if kinds:
            entry["kinds"] = kinds
        return entry

    def __repr__(self) -> str:
        return f"StockEntry({self.stock_code}, {self.name!r}, {self.exchange})"


class HKEXStockRegistry:
    """港交所全量股票注册表。"""

    def __init__(self, cache_dir: str = "./data/.cfm_state", ttl_hours: int = 24):
        self._cache_dir = cache_dir
        self._ttl_hours = ttl_hours
        self._db_path = os.path.join(cache_dir, "hkex_stocks.db")
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def initialize(self) -> None:
        os.makedirs(self._cache_dir, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stocks (
                    stock_code TEXT PRIMARY KEY,
                    name       TEXT DEFAULT '',
                    exchange   TEXT NOT NULL DEFAULT 'SEHK',
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_hkex_stocks_exchange
                ON stocks(exchange)
                """
            )
            self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def is_fresh(self) -> bool:
        if not self._conn:
            return False
        with self._lock:
            row = self._conn.execute("SELECT MAX(updated_at) AS latest FROM stocks").fetchone()
        if not row or not row["latest"]:
            return False
        try:
            last = datetime.fromisoformat(row["latest"])
            now = datetime.now(timezone.utc)
            elapsed_hours = (now - last).total_seconds() / 3600
            return elapsed_hours < self._ttl_hours
        except (ValueError, TypeError):
            return False

    def refresh(self, force: bool = False) -> int:
        if not force and self.is_fresh():
            logger.debug("HKEX stock registry cache is fresh, skipping refresh")
            return self.count()

        logger.info("Refreshing HKEX stock registry...")
        try:
            resp = http_get(STOCK_LIST_URL)
            data = resp.json()
        except Exception as exc:
            logger.error("Failed to fetch HKEX stock list: %s", exc)
            return 0

        if not data or not isinstance(data, list):
            logger.warning("HKEX returned empty or invalid stock list")
            return 0

        now = datetime.now(timezone.utc).isoformat()
        count = 0
        with self._lock:
            self._conn.execute("DELETE FROM stocks")
            for item in data:
                code = (item.get("c") or "").strip()
                if not code:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO stocks (stock_code, name, exchange, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        code,
                        (item.get("n") or "").strip(),
                        "SEHK",
                        now,
                    ),
                )
                count += 1
            self._conn.commit()

        logger.info(
            "HKEX stock registry refreshed: %d stocks cached (from %d API entries)",
            count,
            len(data),
        )
        return count

    def get_all(self) -> list[StockEntry]:
        if not self._conn:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT stock_code, name, exchange FROM stocks ORDER BY stock_code"
            ).fetchall()

        return [
            StockEntry(
                stock_code=row["stock_code"],
                name=row["name"],
                exchange=row["exchange"],
            )
            for row in rows
        ]

    def get_hk_stocks(self) -> list[StockEntry]:
        return self.get_all()

    def count(self) -> int:
        if not self._conn:
            return 0
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM stocks").fetchone()
        return int(row[0]) if row else 0

    def lookup(self, stock_code: str) -> StockEntry | None:
        if not self._conn:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT stock_code, name, exchange FROM stocks WHERE stock_code = ?",
                (stock_code,),
            ).fetchone()
        if not row:
            return None
        return StockEntry(
            stock_code=row["stock_code"],
            name=row["name"],
            exchange=row["exchange"],
        )
