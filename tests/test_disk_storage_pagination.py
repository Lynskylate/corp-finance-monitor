import shutil
import unittest

from corp_finance_monitor.core.config import StorageConfig
from corp_finance_monitor.core.model import FilingKind, FilingRef
from corp_finance_monitor.storage.disk import DiskStorage
from tests.conftest import temp_dir  # noqa: F401


class TestDiskStoragePagination(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir("disk_storage_pagination")
        self.storage = DiskStorage(StorageConfig(backend="disk", base_dir=self.tmp))
        self.storage.initialize()

    def tearDown(self):
        try:
            self.storage.close()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_refs_limit_offset_and_count(self):
        refs = [
            FilingRef(
                source="cninfo",
                source_id=f"id-{idx:03d}",
                stock_code="000725",
                stock_name="BOE",
                title=f"公告 {idx}",
                kind=FilingKind.ANNUAL,
                published_at=f"2025-04-{idx:02d}",
                url="",
            )
            for idx in range(1, 6)
        ]
        for ref in refs:
            self.storage.upsert_metadata(ref)

        total = self.storage.count_refs(source="cninfo", stock_code="000725")
        page = self.storage.list_refs(
            source="cninfo",
            stock_code="000725",
            limit=2,
            offset=1,
        )

        self.assertEqual(total, 5)
        self.assertEqual([ref.source_id for ref in page], ["id-004", "id-003"])

    def test_list_refs_offset_without_limit(self):
        refs = [
            FilingRef(
                source="cninfo",
                source_id=f"id-{idx:03d}",
                stock_code="000636",
                stock_name="FHGK",
                title=f"分页公告 {idx}",
                kind=FilingKind.SEMI,
                published_at=f"2025-05-{idx:02d}",
                url="",
            )
            for idx in range(1, 4)
        ]
        for ref in refs:
            self.storage.upsert_metadata(ref)

        page = self.storage.list_refs(source="cninfo", stock_code="000636", offset=1)
        self.assertEqual([ref.source_id for ref in page], ["id-002", "id-001"])


if __name__ == "__main__":
    unittest.main()
