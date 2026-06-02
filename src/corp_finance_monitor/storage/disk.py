from __future__ import annotations
import os
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from corp_finance_monitor.core.model import FilingRef, Filing, FilingKind
from corp_finance_monitor.core.storage import AbstractStorage
from corp_finance_monitor.core.config import StorageConfig


class DiskStorage(AbstractStorage):
    """
    本地磁盘存储

    目录结构:
    {base_dir}/
      filings/
        {source}/
          {stock_code}/
            {kind}/
              {published_at}_{source_id}_{title}.pdf
      .cfm_state/
        state.db          # 元数据库
        meta.db           # 文件索引
    """

    def __init__(self, config: StorageConfig):
        self.base_dir = config.base_dir or "./data"
        self.filings_dir = os.path.join(self.base_dir, "filings")
        self._meta_db: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def initialize(self):
        os.makedirs(self.filings_dir, exist_ok=True)
        meta_dir = os.path.join(self.base_dir, ".cfm_state")
        os.makedirs(meta_dir, exist_ok=True)
        self._meta_db = sqlite3.connect(
            os.path.join(meta_dir, "meta.db"),
            check_same_thread=False,
        )
        self._meta_db.row_factory = sqlite3.Row
        self._meta_db.execute("""
            CREATE TABLE IF NOT EXISTS filings (
                unique_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                stock_code TEXT,
                stock_name TEXT,
                title TEXT,
                kind TEXT,
                published_at TEXT,
                stored_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                url TEXT DEFAULT '',
                stored_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._meta_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_meta_source
            ON filings(source)
        """)
        self._meta_db.execute("""
            CREATE INDEX IF NOT EXISTS idx_meta_stock
            ON filings(stock_code)
        """)
        self._meta_db.commit()

    def _build_path(self, ref: FilingRef) -> str:
        date_part = ref.published_at[:10] if ref.published_at else "unknown"
        safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in ref.title)[:80]
        filename = f"{date_part}_{ref.source_id}_{safe_title}.pdf"
        rel = os.path.join(
            ref.source,
            ref.stock_code or "unknown",
            ref.kind.value,
            filename,
        )
        return os.path.join(self.filings_dir, rel)

    def exists(self, ref: FilingRef) -> bool:
        if self._meta_db:
            with self._lock:
                cursor = self._meta_db.execute(
                    "SELECT 1 FROM filings WHERE unique_key = ?", (ref.unique_key,)
                )
                if cursor.fetchone():
                    return True
        stored_path = self._build_path(ref)
        return os.path.exists(stored_path) and os.path.getsize(stored_path) > 100

    def store(self, filing: Filing) -> str:
        stored_path = self._build_path(filing.ref)
        Path(stored_path).parent.mkdir(parents=True, exist_ok=True)
        with open(stored_path, "wb") as f:
            f.write(filing.content)
        filing.stored_path = stored_path
        self.upsert_metadata(filing.ref, stored_path=stored_path, file_size=filing.file_size)
        return stored_path

    def upsert_metadata(self, ref: FilingRef, stored_path: str = "", file_size: int = 0):
        if not self._meta_db:
            return
        final_path = stored_path or self.get_path(ref) or self._build_path(ref)
        with self._lock:
            self._meta_db.execute(
                """INSERT OR REPLACE INTO filings
                   (unique_key, source, source_id, stock_code, stock_name,
                    title, kind, published_at, stored_path, file_size, url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ref.unique_key,
                    ref.source,
                    ref.source_id,
                    ref.stock_code,
                    ref.stock_name,
                    ref.title,
                    ref.kind.value,
                    ref.published_at,
                    final_path,
                    file_size,
                    ref.url,
                ),
            )
            self._meta_db.commit()

    def get(self, ref: FilingRef) -> Optional[Filing]:
        path = self.get_path(ref) or self._build_path(ref)

        if os.path.exists(path) and os.path.getsize(path) > 100:
            with open(path, "rb") as f:
                content = f.read()
            return Filing(ref=ref, content=content, stored_path=path)
        return None

    def get_path(self, ref: FilingRef) -> Optional[str]:
        if self._meta_db:
            with self._lock:
                cursor = self._meta_db.execute(
                    "SELECT stored_path FROM filings WHERE unique_key = ?",
                    (ref.unique_key,),
                )
                row = cursor.fetchone()
                if row:
                    return row["stored_path"]
        candidate = self._build_path(ref)
        if os.path.exists(candidate):
            return candidate
        return None

    def find_ref(self, source: str, source_id: str) -> Optional[FilingRef]:
        if not self._meta_db:
            return None
        with self._lock:
            row = self._meta_db.execute(
                """
                SELECT source, source_id, stock_code, stock_name, title, kind, published_at, url, file_size
                FROM filings
                WHERE source = ? AND source_id = ?
                """,
                (source, source_id),
            ).fetchone()
        if not row:
            return None
        return FilingRef(
            source=row["source"],
            source_id=row["source_id"],
            stock_code=row["stock_code"] or "",
            stock_name=row["stock_name"] or "",
            title=row["title"] or "",
            kind=FilingKind(row["kind"]) if row["kind"] else FilingKind.OTHER,
            published_at=row["published_at"] or "",
            url=row["url"] or "",
            file_size=row["file_size"] or 0,
        )

    def _build_ref_filters(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        kind: Optional[FilingKind] = None,
        since: Optional[str] = None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if stock_code:
            clauses.append("stock_code = ?")
            params.append(stock_code)
        if kind:
            clauses.append("kind = ?")
            params.append(kind.value)
        if since:
            clauses.append("published_at >= ?")
            params.append(since)
        where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where_clause, params

    def list_refs(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        kind: Optional[FilingKind] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[FilingRef]:
        if not self._meta_db:
            return []
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        query = (
            "SELECT source, source_id, stock_code, stock_name, title, kind, published_at, stored_path, url, file_size "
            "FROM filings"
        )
        where_clause, params = self._build_ref_filters(
            source=source,
            stock_code=stock_code,
            kind=kind,
            since=since,
        )
        query += where_clause
        query += " ORDER BY published_at DESC, source_id DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)

        with self._lock:
            cursor = self._meta_db.execute(query, params)
            rows = cursor.fetchall()
        refs = []
        for row in rows:
            refs.append(
                FilingRef(
                    source=row["source"], source_id=row["source_id"], stock_code=row["stock_code"] or "",
                    stock_name=row["stock_name"] or "", title=row["title"] or "",
                    kind=FilingKind(row["kind"]) if row["kind"] else FilingKind.OTHER,
                    published_at=row["published_at"] or "",
                    url=row["url"] or "",
                    file_size=row["file_size"] or 0,
                )
            )
        return refs

    def count_refs(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        kind: Optional[FilingKind] = None,
        since: Optional[str] = None,
    ) -> int:
        if not self._meta_db:
            return 0
        query = "SELECT COUNT(*) FROM filings"
        where_clause, params = self._build_ref_filters(
            source=source,
            stock_code=stock_code,
            kind=kind,
            since=since,
        )
        query += where_clause
        with self._lock:
            row = self._meta_db.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    def list_distinct_sources(self) -> List[str]:
        if not self._meta_db:
            return []
        with self._lock:
            rows = self._meta_db.execute(
                "SELECT DISTINCT source FROM filings"
            ).fetchall()
        return [row["source"] for row in rows]

    def list_distinct_kinds(self) -> List[str]:
        if not self._meta_db:
            return []
        with self._lock:
            rows = self._meta_db.execute(
                "SELECT DISTINCT kind FROM filings WHERE kind IS NOT NULL AND kind != ''"
            ).fetchall()
        return [row["kind"] for row in rows]

    def delete(self, ref: FilingRef) -> bool:
        path = self.get_path(ref) or self._build_path(ref)
        deleted = False
        if os.path.exists(path):
            os.remove(path)
            deleted = True
        if self._meta_db:
            with self._lock:
                self._meta_db.execute(
                    "DELETE FROM filings WHERE unique_key = ?", (ref.unique_key,)
                )
                self._meta_db.commit()
        return deleted

    def close(self):
        if self._meta_db:
            self._meta_db.close()
            self._meta_db = None
