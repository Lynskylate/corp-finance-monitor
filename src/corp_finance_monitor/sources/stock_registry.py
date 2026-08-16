"""
Stock Registry — 自动获取并缓存 cninfo 全量股票列表。

数据源: http://www.cninfo.com.cn/new/data/szse_stock.json
该接口一次返回全量 A/B 股 + CDR 列表（约 6000 条），无需分页。

本地缓存: data/.cfm_state/stocks.db (SQLite)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from collections.abc import Sequence
from datetime import datetime, timezone

from .base import http_get

logger = logging.getLogger("cfm.stock_registry")

STOCK_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"

# 境内权益覆盖范围：A股 + B股 + CDR。
# BSE 920 号段由旧 4/8 号段改码而来，registry 中新旧双码并存（共享 orgId）。
DOMESTIC_EQUITY_CATEGORIES = ("A股", "B股", "CDR")


def _infer_exchange(code: str) -> str:
    """
    根据股票代码前缀推断交易所。

    规则:
      0/2/3 开头 → SZSE
      4/8/920 开头 → BSE (北交所)
      其他       → SSE
    """
    if code.startswith(("0", "2", "3")):
        return "SZSE"
    if code.startswith("920") or code.startswith(("4", "8")):
        return "BSE"
    return "SSE"


class StockEntry:
    """单只股票的注册信息。"""

    __slots__ = ("category", "exchange", "name", "org_id", "stock_code")

    def __init__(
        self,
        stock_code: str,
        org_id: str,
        name: str = "",
        exchange: str = "",
        category: str = "",
    ):
        self.stock_code = stock_code
        self.org_id = org_id
        self.name = name
        self.exchange = exchange
        self.category = category

    def to_watchlist_entry(self, kinds: list[str] | None = None) -> dict:
        """转换为与 config.yaml watchlist 条目相同的格式，供 CninfoSource.discover 使用。"""
        entry = {"stock": self.stock_code, "org_id": self.org_id}
        if kinds:
            entry["kinds"] = kinds
        return entry

    def __repr__(self) -> str:
        return f"StockEntry({self.stock_code}, {self.org_id}, {self.name!r}, {self.exchange})"


class CninfoStockRegistry:
    """
    cninfo 全量股票注册表。

    - 从 cninfo API 拉取全量股票列表
    - 本地 SQLite 缓存，支持 TTL 过期刷新
    - 失败时 graceful degradation：返回空列表，不 crash
    """

    def __init__(self, cache_dir: str = "./data/.cfm_state", ttl_hours: int = 24):
        self._cache_dir = cache_dir
        self._ttl_hours = ttl_hours
        self._db_path = os.path.join(cache_dir, "stocks.db")
        self._conn: sqlite3.Connection | None = None
        self._alias_map: dict[str, tuple[str, ...]] | None = None
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
                    org_id     TEXT NOT NULL,
                    name       TEXT DEFAULT '',
                    exchange   TEXT NOT NULL,
                    category   TEXT DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_stocks_exchange
                ON stocks(exchange)
                """
            )
            self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def is_fresh(self) -> bool:
        """缓存是否在 TTL 有效期内。"""
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
        """
        从 cninfo 拉取最新股票列表并更新缓存。

        Returns:
            更新后的股票总数。失败返回 0。
        """
        if not force and self.is_fresh():
            logger.debug("Stock registry cache is fresh, skipping refresh")
            return self.count()

        logger.info("Refreshing stock registry from cninfo...")
        try:
            resp = http_get(STOCK_LIST_URL)
            data = resp.json()
        except Exception as exc:
            logger.error("Failed to fetch stock list from cninfo: %s", exc)
            return 0

        stock_list = data.get("stockList") or []
        if not stock_list:
            logger.warning("cninfo returned empty stock list")
            return 0

        now = datetime.now(timezone.utc).isoformat()
        count = 0
        with self._lock:
            self._alias_map = None  # 代码集已变，alias map 需重建
            self._conn.execute("DELETE FROM stocks")
            for item in stock_list:
                code = (item.get("code") or "").strip()
                org_id = (item.get("orgId") or "").strip()
                if not code or not org_id:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO stocks (stock_code, org_id, name, exchange, category, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        org_id,
                        (item.get("zwjc") or "").strip(),
                        _infer_exchange(code),
                        (item.get("category") or "").strip(),
                        now,
                    ),
                )
                count += 1
            self._conn.commit()

        logger.info(
            "Stock registry refreshed: %d stocks cached (from %d API entries)",
            count,
            len(stock_list),
        )
        return count

    def get_all(
        self,
        exchange: str | None = None,
        category: str | None = None,
        categories: Sequence[str] | None = None,
    ) -> list[StockEntry]:
        if not self._conn:
            return []
        query = "SELECT stock_code, org_id, name, exchange, category FROM stocks WHERE 1=1"
        params: list[str] = []
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)
        if categories:
            # 多 category 过滤（优先于单 category）
            placeholders = ",".join("?" for _ in categories)
            query += f" AND category IN ({placeholders})"
            params.extend(categories)
        elif category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY stock_code"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()

        return [
            StockEntry(
                stock_code=row["stock_code"],
                org_id=row["org_id"],
                name=row["name"],
                exchange=row["exchange"],
                category=row["category"],
            )
            for row in rows
        ]

    def get_a_shares(self) -> list[StockEntry]:
        """境内权益全量列表：A股 + B股 + CDR。

        历史上精确过滤 category='A股'，导致 79 家 B股（200xxx）与 CDR
        （689xxx）从未进入 full-market 扫描。现按 DOMESTIC_EQUITY_CATEGORIES
        覆盖（方法名保留以兼容既有调用方）。
        """
        return self.get_all(categories=DOMESTIC_EQUITY_CATEGORIES)

    def get_stock_codes(self) -> list[str]:
        """Return stock codes for all A-shares via a generic registry interface."""
        return [entry.stock_code for entry in self.get_a_shares()]

    def get_code_aliases(self, stock_code: str) -> list[str]:
        """返回与给定代码共享 orgId 的全部代码（含自身），排序保证确定性。

        BSE 920 号段由旧 4/8 号段改码而来，registry 中同一公司新旧双码并存
        （如 833454/920454 → gfbj0833454）。cninfo 公告按旧码返回，因此
        查询侧需按 orgId 分组做新旧码归一。未知代码返回 [stock_code]。
        """
        if not self._conn:
            return [stock_code]
        with self._lock:
            self._ensure_alias_map()
            return list(self._alias_map.get(stock_code, (stock_code,)))

    def _ensure_alias_map(self) -> None:
        """惰性构建 orgId → 代码组 的 alias map（调用方需持 self._lock）。"""
        if self._alias_map is not None:
            return
        alias_map: dict[str, tuple[str, ...]] = {}
        rows = self._conn.execute(
            "SELECT stock_code, org_id FROM stocks WHERE org_id != ''"
        ).fetchall()
        by_org: dict[str, list[str]] = {}
        for row in rows:
            by_org.setdefault(row["org_id"], []).append(row["stock_code"])
        for codes in by_org.values():
            if len(codes) > 1:
                group = tuple(sorted(codes))
                for code in group:
                    alias_map[code] = group
        self._alias_map = alias_map

    def count(self, exchange: str | None = None) -> int:
        if not self._conn:
            return 0
        query = "SELECT COUNT(*) FROM stocks"
        params: list[str] = []
        if exchange:
            query += " WHERE exchange = ?"
            params.append(exchange)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    def lookup(self, stock_code: str) -> StockEntry | None:
        if not self._conn:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT stock_code, org_id, name, exchange, category FROM stocks WHERE stock_code = ?",
                (stock_code,),
            ).fetchone()
        if not row:
            return None
        return StockEntry(
            stock_code=row["stock_code"],
            org_id=row["org_id"],
            name=row["name"],
            exchange=row["exchange"],
            category=row["category"],
        )
