"""
上交所 (sse.com.cn) — IPO招股书 Source
API: GET query.sse.com.cn/commonSoaQuery.do (JSONP)
"""
import json
import random
import re
import time
from typing import List, Optional, Sequence

from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.core.model import FilingRef, Filing, FilingKind
from .base import http_get, parse_timestamp

QUERY_URL = "https://query.sse.com.cn/commonSoaQuery.do"
PDF_BASE = "https://static.sse.com.cn/stock"


def _jsonp_clean(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^jsonpCallback\d+\(", "", text)
    text = re.sub(r"\)\s*$", "", text)
    return json.loads(text)


class SSESource(AbstractSource):
    def discover(
        self,
        watchlist: Optional[List[dict]] = None,
        since: Optional[str] = None,
        only_stock_codes: Optional[Sequence[str]] = None,
    ) -> List[FilingRef]:
        refs = []
        for entry in (watchlist or self.watchlist):
            keyword = entry.get("keyword", "")
            market = entry.get("market", "1,2")

            # 1. 搜索项目列表
            cb = f"jsonpCallback{random.randint(10000, 99999)}"
            params = {
                "isPagination": "true",
                "sqlId": "SH_XM_LB",
                "pageHelp.pageSize": "50",
                "pageHelp.pageNo": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.endPage": "1",
                "pageHelp.cacheSize": "1",
                "issueMarketType": market,
                "keyword": keyword,
                "order": "updateDate|desc,stockAuditNum|desc",
                "jsonCallBack": cb,
                "_": str(int(time.time() * 1000)),
            }

            # SSE API supports searchDateBegin for date filtering
            if since:
                params["searchDateBegin"] = since
            headers = {"Referer": "https://www.sse.com.cn/listing/renewal/ipo/"}
            resp = http_get(QUERY_URL, headers=headers, params=params)
            data = _jsonp_clean(resp.text)
            projects = data.get("result", [])

            for proj in projects:
                audit_id = proj.get("stockAuditNum", "")
                if not audit_id:
                    continue
                issuer = (proj.get("stockIssuer") or [{}])[0]
                company_name = issuer.get("s_issueCompanyFullName", "")

                # 2. 获取该项目的文件列表
                cb2 = f"jsonpCallback{random.randint(10000, 99999)}"
                params2 = {
                    "sqlId": "GP_COMMON_FILE_SEARCH",
                    "auditId": audit_id,
                    "marketType": market,
                    "isPagination": "false",
                    "jsonCallBack": cb2,
                    "_": str(int(time.time() * 1000)),
                }
                resp2 = http_get(QUERY_URL, headers=headers, params=params2)
                data2 = _jsonp_clean(resp2.text)
                files = data2.get("result", [])

                for f in files:
                    if str(f.get("fileType", "")) != "30":
                        continue  # 只取招股说明书
                    file_path = f.get("filePath", "")
                    if not file_path:
                        continue
                    title = f.get("fileTitle", company_name)
                    date = parse_timestamp(f.get("fileUpdTime", ""))
                    pdf_url = f"{PDF_BASE}/{file_path.lstrip('/')}"

                    ref = FilingRef(
                        source="sse",
                        source_id=f"audit_{audit_id}_{f.get('fileVersion', '1')}",
                        stock_code=audit_id,
                        stock_name=company_name,
                        title=title,
                        kind=FilingKind.PROSPECTUS,
                        published_at=date,
                        url=pdf_url,
                    )
                    refs.append(ref)

        return refs

    def fetch(self, ref: FilingRef) -> Optional[Filing]:
        if not ref.url:
            return None
        try:
            headers = {"Referer": "https://www.sse.com.cn/listing/renewal/ipo/"}
            resp = http_get(ref.url, headers=headers)
            return Filing(ref=ref, content=resp.content)
        except Exception:
            return None
