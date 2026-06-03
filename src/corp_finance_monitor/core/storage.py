from __future__ import annotations

from abc import ABC, abstractmethod

from .model import Filing, FilingKind, FilingRef


class AbstractStorage(ABC):
    """
    存储抽象

    负责财报文件的持久化、去重和查询。
    默认实现: DiskStorage (本地文件系统)
    可扩展: S3Storage, DBStorage
    """

    @abstractmethod
    def exists(self, ref: FilingRef) -> bool:
        """检查是否已存储（用于去重）"""
        ...

    @abstractmethod
    def store(self, filing: Filing) -> str:
        """
        存储财报文件。
        返回存储路径。
        """
        ...

    @abstractmethod
    def upsert_metadata(self, ref: FilingRef, stored_path: str = "", file_size: int = 0):
        """仅更新元数据索引，不改写文件内容。"""
        ...

    @abstractmethod
    def get(self, ref: FilingRef) -> Filing | None:
        """获取已存储的财报"""
        ...

    @abstractmethod
    def get_path(self, ref: FilingRef) -> str | None:
        """获取已存储文件路径"""
        ...

    @abstractmethod
    def find_ref(self, source: str, source_id: str) -> FilingRef | None:
        """按 source/source_id 查找引用"""
        ...

    @abstractmethod
    def list_refs(
        self,
        source: str | None = None,
        stock_code: str | None = None,
        kind: FilingKind | None = None,
        since: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        exchange: str | None = None,
    ) -> list[FilingRef]:
        """按条件查询已存储的财报引用"""
        ...

    @abstractmethod
    def count_refs(
        self,
        source: str | None = None,
        stock_code: str | None = None,
        kind: FilingKind | None = None,
        since: str | None = None,
        exchange: str | None = None,
    ) -> int:
        """按条件统计已存储的财报引用数量"""
        ...

    @abstractmethod
    def list_distinct_sources(self) -> list[str]:
        """返回所有不重复的数据源名称"""
        ...

    @abstractmethod
    def list_distinct_kinds(self) -> list[str]:
        """返回所有不重复的报告类型"""
        ...

    @abstractmethod
    def delete(self, ref: FilingRef) -> bool:
        """删除已存储的财报"""
        ...
