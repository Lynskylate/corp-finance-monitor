"""Tests for DiskStorage stock_codes IN-filter (BSE dual-code alias query expansion)."""

import shutil
import unittest

from corp_finance_monitor.core.config import StorageConfig
from corp_finance_monitor.core.model import FilingKind, FilingRef
from corp_finance_monitor.storage.disk import DiskStorage
from tests.conftest import temp_dir


def _ref(source_id: str, stock_code: str, published_at: str) -> FilingRef:
    return FilingRef(
        source="cninfo",
        source_id=source_id,
        stock_code=stock_code,
        stock_name="同心传动",
        title=f"公告 {source_id}",
        kind=FilingKind.SEMI,
        published_at=published_at,
        url="",
    )


class TestDiskStorageStockCodesFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir("disk_storage_stock_codes")
        self.storage = DiskStorage(StorageConfig(backend="disk", base_dir=self.tmp))
        self.storage.initialize()
        # 旧码 833454 两条 + 新码 920454 一条 + 无关 000001 一条
        for ref in [
            _ref("old-001", "833454", "2026-04-10"),
            _ref("old-002", "833454", "2026-04-20"),
            _ref("new-001", "920454", "2026-04-15"),
            _ref("sz-001", "000001", "2026-04-18"),
        ]:
            self.storage.upsert_metadata(ref)

    def tearDown(self):
        try:
            self.storage.close()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_count_refs_stock_codes_in_filter(self):
        self.assertEqual(self.storage.count_refs(stock_codes=["833454", "920454"]), 3)
        self.assertEqual(self.storage.count_refs(stock_codes=["920454"]), 1)
        self.assertEqual(self.storage.count_refs(stock_codes=["999999"]), 0)

    def test_list_refs_stock_codes_in_filter(self):
        refs = self.storage.list_refs(stock_codes=["833454", "920454"])
        self.assertEqual(
            sorted(ref.source_id for ref in refs),
            ["new-001", "old-001", "old-002"],
        )

    def test_stock_codes_takes_priority_over_stock_code(self):
        # IN 过滤优先：stock_code=000001 被忽略，仅返回 833454 行
        refs = self.storage.list_refs(stock_code="000001", stock_codes=["833454"])
        self.assertEqual([ref.stock_code for ref in refs], ["833454", "833454"])

    def test_single_stock_code_still_exact(self):
        # storage 层不做隐式 alias 展开（归一是 engine.resolve_stock_codes 职责）
        refs = self.storage.list_refs(stock_code="920454")
        self.assertEqual([ref.source_id for ref in refs], ["new-001"])


if __name__ == "__main__":
    unittest.main()
