"""
巨潮资讯网 (cninfo.com.cn) — A股定期报告 Source
API: POST /new/hisAnnouncement/query
"""
from typing import List, Optional

from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.core.model import FilingRef, Filing, FilingKind
from .base import http_post, http_get, parse_timestamp

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
    def discover(self, watchlist: Optional[List[dict]] = None) -> List[FilingRef]:
        refs = []
        for entry in (watchlist or self.watchlist):
            stock = entry.get("stock", "")
            org_id = entry.get("org_id", "")
            kinds = entry.get("kinds", ["annual", "semi", "q1", "q3"])
            limit = int(entry.get("limit", 0) or 0)

            stock_param = f"{stock},{org_id}" if org_id else stock
            category = ";".join(
                CATEGORY_MAP[k] for k in kinds if k in CATEGORY_MAP
            ) or ALL_KINDS

            # 确定板块
            if stock.startswith(("0", "2", "3")):
                column = "szse"
            elif stock.startswith(("4", "8")):
                column = "bj"
            else:
                column = "sse"

            page = 1
            while True:
                data = {
                    "pageNum": str(page),
                    "pageSize": "30",
                    "column": column,
                    "tabName": "fulltext",
                    "stock": stock_param,
                    "category": category,
                    "seDate": "",
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
                items = result.get("announcements", [])

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

    def fetch(self, ref: FilingRef) -> Optional[Filing]:
        if not ref.url:
            return None
        try:
            resp = http_get(ref.url)
            return Filing(ref=ref, content=resp.content)
        except Exception:
            return None
