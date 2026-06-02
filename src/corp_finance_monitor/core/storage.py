from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
from .model import FilingRef, Filing, FilingKind


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
    def get(self, ref: FilingRef) -> Optional[Filing]:
        """获取已存储的财报"""
        ...

    @abstractmethod
    def get_path(self, ref: FilingRef) -> Optional[str]:
        """获取已存储文件路径"""
        ...

    @abstractmethod
    def find_ref(self, source: str, source_id: str) -> Optional[FilingRef]:
        """按 source/source_id 查找引用"""
        ...

    @abstractmethod
    def list_refs(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        kind: Optional[FilingKind] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[FilingRef]:
        """按条件查询已存储的财报引用"""
        ...

    @abstractmethod
    def count_refs(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        kind: Optional[FilingKind] = None,
        since: Optional[str] = None,
    ) -> int:
        """按条件统计已存储的财报引用数量"""
        ...

    @abstractmethod
    def delete(self, ref: FilingRef) -> bool:
        """删除已存储的财报"""
        ...
