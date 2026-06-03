"""
巨潮资讯网 (cninfo.com.cn) — A股定期报告 Source
API: POST /new/hisAnnouncement/query

支持两种模式:
  - watchlist 模式 (默认): 按 config watchlist 逐股票 discover
  - full_market 模式: 通过 CninfoStockRegistry 获取全量 A 股列表批量 discover
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from corp_finance_monitor.core.config import SourceConfig
from corp_finance_monitor.core.model import Filing, FilingKind, FilingRef
from corp_finance_monitor.core.source import AbstractSource

if TYPE_CHECKING:
    from .stock_registry import CninfoStockRegistry

from .base import http_get, http_post, parse_timestamp

logger = logging.getLogger("cfm.source.cninfo")

API_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE = "https://static.cninfo.com.cn"
ALL_KINDS = "category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh;category_sjdbg_szsh"

CATEGORY_MAP = {
    "annual": "category_ndbg_szsh",
    "semi": "category_bndbg_szsh",
    "q1": "category_yjdbg_szsh",
    "q3": "category_sjdbg_szsh",
}


def _detect_kind(title: str) -> FilingKind:
    # NOTE on intent: the rule below is intentionally asymmetric on purpose
    # and verified by tests/test_cninfo_classification.py:
    #   * "半年度报告摘要" / "中期报告"     -> SEMI  (摘要不过滤, 仍视为中报)
    #   * "年度报告摘要"                  -> OTHER (年报摘要被排除)
    # Rationale: 半年报披露窗口短, 摘要与正文差异较小, 工程上归入同一类
    # 便于下游按 kind 拉取; 年报摘要与年报正文差异大, 单独归类避免误用。
    if "半年度报告" in title or "中期报告" in title:
        return FilingKind.SEMI
    if "一季度报告" in title or "第一季度" in title:
        return FilingKind.Q1
    if "三季度报告" in title or "第三季度" in title:
        return FilingKind.Q3
    if "年度报告" in title and "半年度" not in title and "摘要" not in title:
        return FilingKind.ANNUAL
    return FilingKind.OTHER


class CninfoSource(AbstractSource):
    def __init__(self, name: str, config: SourceConfig):
        super().__init__(name, config)
        self._registry: CninfoStockRegistry | None = None

    @property
    def _full_market(self) -> bool:
        return bool(self.options.get("full_market", False))

    def _get_registry(self) -> CninfoStockRegistry:
        """Lazily initialize CninfoStockRegistry."""
        if self._registry is None:
            from .stock_registry import CninfoStockRegistry

            cache_dir = self.options.get("registry_cache_dir", "./data/.cfm_state")
            self._registry = CninfoStockRegistry(cache_dir=cache_dir)
            self._registry.initialize()
            self._registry.refresh()
        return self._registry

    def discover(
        self,
        watchlist: list[dict] | None = None,
        since: str | None = None,
        only_stock_codes: Sequence[str] | None = None,
    ) -> list[FilingRef]:
        if self._full_market:
            return self._discover_full_market(
                since=since,
                only_stock_codes=only_stock_codes,
            )
        return self._discover_watchlist(watchlist=watchlist, since=since)

    def _discover_watchlist(
        self,
        watchlist: list[dict] | None = None,
        since: str | None = None,
    ) -> list[FilingRef]:
        """Original watchlist-based discover logic (unchanged)."""
        refs = []
        for entry in watchlist or self.watchlist:
            stock = entry.get("stock", "")
            org_id = entry.get("org_id", "")
            kinds = entry.get("kinds", ["annual", "semi", "q1", "q3"])
            limit = int(entry.get("limit", 0) or 0)

            refs.extend(self._discover_single_stock(stock, org_id, kinds, since, limit))
            if limit and len(refs) >= limit:
                return refs[:limit]
        return refs

    def _discover_full_market(
        self,
        since: str | None = None,
        only_stock_codes: Sequence[str] | None = None,
    ) -> list[FilingRef]:
        """Full market mode: use registry to scan all A-shares."""
        refs: list[FilingRef] = []
        try:
            registry = self._get_registry()
        except Exception as exc:
            logger.error("Failed to initialize stock registry: %s", exc)
            return refs

        stocks = registry.get_a_shares()
        logger.info("Registry loaded: %d stocks total", len(stocks))

        if only_stock_codes:
            allowed = set(only_stock_codes)
            stocks = [entry for entry in stocks if entry.stock_code in allowed]
            logger.info("Filtered to %d stocks by only_stock_codes", len(stocks))

        limit = int(self.options.get("full_market_limit", 0) or 0)
        if limit:
            stocks = stocks[:limit]

        for idx, entry in enumerate(stocks, 1):
            kinds = self.options.get("kinds", ["annual", "semi", "q1", "q3"])
            wl = entry.to_watchlist_entry(kinds=kinds)
            stock = wl["stock"]
            org_id = wl.get("org_id", "")

            refs.extend(self._discover_single_stock(stock, org_id, kinds, since))

            if idx % 100 == 0:
                logger.info(
                    "Full-market discover progress: %d/%d stocks, %d refs so far",
                    idx,
                    len(stocks),
                    len(refs),
                )

        logger.info(
            "Full-market discover complete: %d stocks scanned, %d refs", len(stocks), len(refs)
        )
        return refs

    def _discover_single_stock(
        self,
        stock: str,
        org_id: str,
        kinds: list[str],
        since: str | None = None,
        limit: int = 0,
    ) -> list[FilingRef]:
        """Discover filings for a single stock."""
        refs: list[FilingRef] = []

        stock_param = f"{stock},{org_id}" if org_id else stock
        category = ";".join(CATEGORY_MAP[k] for k in kinds if k in CATEGORY_MAP) or ALL_KINDS

        # 确定板块
        if stock.startswith(("0", "2", "3")):
            column = "szse"
        elif stock.startswith(("4", "8")):
            column = "bj"
        else:
            column = "sse"

        # Build date range: since~today (API-level filter)
        from datetime import datetime as dt

        se_date = ""
        if since:
            end_date = dt.utcnow().strftime("%Y-%m-%d")
            se_date = f"{since}~{end_date}"

        page = 1
        while True:
            data = {
                "pageNum": str(page),
                "pageSize": "30",
                "column": column,
                "tabName": "fulltext",
                "stock": stock_param,
                "category": category,
                "seDate": se_date,
                "sortName": "",
                "sortType": "desc",
                "isHLtitle": "true",
            }
            headers = {
                "Referer": f"https://www.cninfo.com.cn/new/disclosure/stock?stockCode={stock}",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            resp = http_post(API_URL, data=data, headers=headers)
            result = resp.json()
            items = result.get("announcements") or []

            for a in items:
                ann_id = str(a.get("announcementId", ""))
                if not ann_id:
                    continue
                title = a.get("announcementTitle", "")
                adj_url = a.get("adjunctUrl", "")
                ts = a.get("announcementTime", 0)
                date = parse_timestamp(ts)
                pdf_url = f"{PDF_BASE}/{adj_url.lstrip('/')}" if adj_url else ""

                ref = FilingRef(
                    source="cninfo",
                    source_id=ann_id,
                    stock_code=stock,
                    stock_name=a.get("secName", ""),
                    title=title,
                    kind=_detect_kind(title),
                    published_at=date,
                    url=pdf_url,
                )
                refs.append(ref)
                if limit and len(refs) >= limit:
                    return refs

            has_more = result.get("hasMore", False)
            if not has_more or page >= 100:
                break
            page += 1

        return refs

    def fetch(self, ref: FilingRef) -> Filing | None:
        if not ref.url:
            return None
        try:
            resp = http_get(ref.url)
            return Filing(ref=ref, content=resp.content)
        except Exception:
            return None

    def close(self):
        """Release resources (registry, etc.)."""
        if self._registry is not None:
            self._registry.close()
            self._registry = None
