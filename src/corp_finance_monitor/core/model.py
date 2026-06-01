from __future__ import annotations
import enum
from dataclasses import dataclass
from typing import Optional


class FilingKind(str, enum.Enum):
    """标准化报告类型枚举"""
    ANNUAL = "annual"           # 年报
    SEMI = "semi"               # 中报/半年报
    Q1 = "q1"                   # 一季报
    Q3 = "q3"                   # 三季报
    PROSPECTUS = "prospectus"   # 招股说明书
    ESG = "esg"                 # ESG报告
    INTERIM = "interim"         # 中期报告（港股）
    QUARTERLY = "quarterly"     # 季度报告（港股）
    OTHER = "other"             # 其他


KIND_LABELS = {
    FilingKind.ANNUAL: "年报",
    FilingKind.SEMI: "中报",
    FilingKind.Q1: "一季报",
    FilingKind.Q3: "三季报",
    FilingKind.PROSPECTUS: "招股书",
    FilingKind.ESG: "ESG报告",
    FilingKind.INTERIM: "中期报告",
    FilingKind.QUARTERLY: "季度报告",
    FilingKind.OTHER: "其他",
}


@dataclass
class FilingRef:
    """
    财报引用 — 用于发现阶段返回的轻量级元数据。
    source 和 source_id 共同构成唯一键，用于去重。
    """
    source: str                # 数据源名称 (e.g. "cninfo", "sse", "hkex")
    source_id: str             # 数据源内部ID (e.g. announcementId)
    stock_code: str            # 股票代码
    stock_name: str = ""       # 公司名称
    title: str = ""            # 文件标题
    kind: FilingKind = FilingKind.OTHER
    published_at: str = ""     # 发布日期 YYYY-MM-DD
    url: str = ""              # 下载URL

    @property
    def unique_key(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass
class Filing:
    """完整财报 — 包含元数据和内容"""
    ref: FilingRef
    content: bytes
    content_type: str = "application/pdf"
    file_size: int = 0
    stored_path: str = ""

    def __post_init__(self):
        self.file_size = len(self.content) if self.content else 0


@dataclass
class RunRecord:
    id: int
    started_at: str
    finished_at: str
    discovered: int
    fetched: int
    failed: int


@dataclass
class Subscription:
    id: Optional[int]
    name: str
    source: str = ""
    stock_code: str = ""
    kind: str = ""
    target: str = ""
    active: bool = True
    created_at: str = ""
    updated_at: str = ""
