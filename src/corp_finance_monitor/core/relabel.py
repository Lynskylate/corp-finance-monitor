"""One-shot kind relabel maintenance — 2026-10 SSE 预告季缺口第 2 失效面（PR #21）.

背景（2026-10-10 janny 发现 + 双侧核验）：
  * 老 `_detect_kind` 仅认「业绩预告」。变体措辞（业绩预增/预减/…）标题
    意外命中 Q1/Q3 子串规则（cninfo.py 的「第三季度」/「第一季度」）或落
    OTHER → 存量 filing_state 出现静默误档（q1=28 / q3=1）。
  * 「业绩快报」在旧分类器下无独立类目 → 存量行误档为 forecast/q1/semi。
  * engine replay 路径 `already_fetched → skip`（engine.py）不会重分类已入
    库行，故重算只能由本维护命令显式执行。

不变量（by construction）：diff 集 ⊆ 标题命中 FORECAST/EXPRESS marker 的行
——无 marker 的行永不进入 plan，即使其存量 kind 与 `_detect_kind` 不一致。
新分类器相对旧分类器仅在 marker 命中处分歧，故该范围同时是完备的。

契约（thread #corp-finance-monitor:95cb6f79，SuperMan GO + janny oracle）：
  * dry-run 默认，输出行级 diff（source_id | from_kind -> to_kind）；
  * `--apply` 才写库，重跑幂等（applied 后 plan 为空）；
  * 验收 = 与独立清单**逐 source_id 对账**，不以计数判 PASS。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from corp_finance_monitor.sources.cninfo import (
    EXPRESS_TITLE_MARKERS,
    FORECAST_TITLE_MARKERS,
    _detect_kind,
)


@dataclass(frozen=True)
class RelabelRow:
    """One planned kind change for an existing filing_state row."""

    unique_key: str
    source: str
    source_id: str
    stock_code: str
    published_at: str
    title: str
    from_kind: str
    to_kind: str


def title_matches_marker(title: str) -> bool:
    """True if the title hits any FORECAST/EXPRESS variant marker."""
    return any(marker in title for marker in FORECAST_TITLE_MARKERS) or any(
        marker in title for marker in EXPRESS_TITLE_MARKERS
    )


def compute_relabel_plan(rows: Iterable[Mapping[str, object]]) -> list[RelabelRow]:
    """Compute the kind-relabel plan over filing_state rows.

    ``rows`` are mappings with keys: unique_key, source, source_id, stock_code,
    title, kind, published_at (``sqlite3.Row`` and ``dict`` both qualify).

    Scope invariant: only rows whose title hits a marker are considered; all
    other rows are skipped unconditionally, so the plan is by construction a
    subset of marker-matching rows.
    """
    plan: list[RelabelRow] = []
    for row in rows:
        title = str(row["title"] or "")
        if not title_matches_marker(title):
            continue
        stored = str(row["kind"] or "")
        new_kind = _detect_kind(title)
        if new_kind.value != stored:
            plan.append(
                RelabelRow(
                    unique_key=str(row["unique_key"]),
                    source=str(row["source"]),
                    source_id=str(row["source_id"]),
                    stock_code=str(row["stock_code"] or ""),
                    published_at=str(row["published_at"] or ""),
                    title=title,
                    from_kind=stored,
                    to_kind=new_kind.value,
                )
            )
    plan.sort(key=lambda r: (r.source, r.published_at, r.source_id))
    return plan
