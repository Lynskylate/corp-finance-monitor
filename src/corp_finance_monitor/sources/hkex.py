"""
港交所披露易 (hkexnews.hk) — 港股财报/招股书 Source
API: GET /search/titleSearchServlet.do

支持两种模式:
  - watchlist 模式 (默认): 按 config watchlist 逐股票 discover
  - full_market 模式: 通过 HKEXStockRegistry 获取全量港股列表批量 discover
"""
import json
import logging
from typing import List, Optional, Sequence

from corp_finance_monitor.core.source import AbstractSource
from corp_finance_monitor.core.model import FilingRef, Filing, FilingKind
from .base import http_get

API_BASE = "https://www1.hkexnews.hk"
SEARCH_URL = f"{API_BASE}/search/titleSearchServlet.do"
STOCK_LIST_URL = f"{API_BASE}/ncms/script/eds/activestock_sehk_e.json"

T1_FINANCIAL = "40000"
T1_LISTING = "30000"

T2_MAP = {
    "annual": "40100",
    "interim": "40200",
    "quarterly": "40300",
    "esg": "40400",
    "prospectus": "30100",
}

logger = logging.getLogger("cfm.source.hkex")


def _fetch_stock_id(stock_code: str) -> int:
    stock_code = stock_code.zfill(5)
    resp = http_get(STOCK_LIST_URL)
    for s in resp.json():
        if s["c"] == stock_code:
            return s["i"]
    raise ValueError(f"Stock code {stock_code} not found on HKEX")


logger = logging.getLogger("cfm.source.hkex")


class HKEXSource(AbstractSource):
    def __init__(self, name: str, config: "SourceConfig"):
        super().__init__(name, config)
        self._registry = None

    @property
    def _full_market(self) -> bool:
        return bool(self.options.get("full_market", False))

    def _get_registry(self):
        if self._registry is None:
            from .hkex_registry import HKEXStockRegistry
            cache_dir = self.options.get("registry_cache_dir", "./data/.cfm_state")
            self._registry = HKEXStockRegistry(cache_dir=cache_dir)
            self._registry.initialize()
            self._registry.refresh()
        return self._registry

    def discover(
        self,
        watchlist: Optional[List[dict]] = None,
        since: Optional[str] = None,
        only_stock_codes: Optional[Sequence[str]] = None,
    ) -> List[FilingRef]:
        if self._full_market:
            return self._discover_full_market(
                since=since,
                only_stock_codes=only_stock_codes,
            )
        return self._discover_watchlist(watchlist=watchlist, since=since)

    def _discover_watchlist(
        self,
        watchlist: Optional[List[dict]] = None,
        since: Optional[str] = None,
    ) -> List[FilingRef]:
        refs = []
        for entry in (watchlist or self.watchlist):
            stock = entry.get("stock", "")
            kinds = entry.get("kinds", ["annual", "interim"])
            refs.extend(self._discover_single_stock(stock, kinds, since))
        return refs

    def _discover_full_market(
        self,
        since: Optional[str] = None,
        only_stock_codes: Optional[Sequence[str]] = None,
    ) -> List[FilingRef]:
        refs: List[FilingRef] = []
        try:
            registry = self._get_registry()
        except Exception as exc:
            logger.error(
                "Failed to initialize HKEX stock registry: %s", exc
            )
            return refs

        stocks = registry.get_hk_stocks()

        if only_stock_codes:
            allowed = {code for code in only_stock_codes}
            stocks = [entry for entry in stocks if entry.stock_code in allowed]

        limit = int(self.options.get("full_market_limit", 0) or 0)
        if limit:
            stocks = stocks[:limit]

        kinds = self.options.get("kinds", ["annual", "interim"])
        for entry in stocks:
            refs.extend(
                self._discover_single_stock(entry.stock_code, kinds, since)
            )

        return refs

    def _discover_single_stock(
        self,
        stock: str,
        kinds: List[str],
        since: Optional[str] = None,
    ) -> List[FilingRef]:
        from datetime import datetime as dt

        refs: List[FilingRef] = []
        stock_code = stock.zfill(5)

        try:
            stock_id = _fetch_stock_id(stock)
        except ValueError:
            return refs

        for kind in kinds:
            t2 = T2_MAP.get(kind)
            if not t2:
                continue
            if kind == "prospectus":
                t1 = T1_LISTING
            else:
                t1 = T1_FINANCIAL

            from_date = "20100101"
            to_date = dt.utcnow().strftime("%Y%m%d")
            if since:
                from_date = since.replace("-", "")

            params = {
                "sortDir": "1",
                "sortByOptions": "DateTime",
                "category": "0",
                "market": "SEHK",
                "stockId": str(stock_id),
                "documentType": "-1",
                "title": "",
                "searchType": "0",
                "t1code": t1,
                "t2Gcode": "-2",
                "t2code": t2,
                "rowRange": "100",
                "lang": "E",
                "fromDate": from_date,
                "toDate": to_date,
            }

            headers = {
                "Referer": f"{API_BASE}/search/titlesearch.xhtml",
                "X-Requested-With": "XMLHttpRequest",
            }
            resp = http_get(SEARCH_URL, headers=headers, params=params)
            data = resp.json()
            result_str = data.get("result", "[]")
            records = json.loads(result_str) if isinstance(result_str, str) else result_str

            for r in records:
                news_id = str(r.get("NEWS_ID", ""))
                if not news_id:
                    continue
                title = r.get("TITLE", "")
                file_link = r.get("FILE_LINK", "")
                date_raw = r.get("DATE_TIME", "")
                date = date_raw.split(" ")[0] if date_raw else ""
                if date:
                    try:
                        date = dt.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
                    except ValueError:
                        pass

                pdf_url = f"{API_BASE}{file_link}" if file_link else ""

                ref = FilingRef(
                    source="hkex",
                    source_id=news_id,
                    stock_code=stock,
                    stock_name=r.get("STOCK_NAME", "").replace("<br/>", "/"),
                    title=title,
                    kind=self._resolve_kind(kind, title),
                    published_at=date,
                    url=pdf_url,
                )
                refs.append(ref)

        return refs

    @staticmethod
    def _resolve_kind(expected: str, title: str) -> FilingKind:
        t = title.upper()
        mapping = [
            (FilingKind.PROSPECTUS, "PROSPECTUS"),
            (FilingKind.ANNUAL, "ANNUAL REPORT"),
            (FilingKind.INTERIM, ("INTERIM REPORT", "HALF-YEAR", "HALF YEAR")),
            (FilingKind.QUARTERLY, "QUARTERLY"),
            (FilingKind.ESG, ("ESG", "ENVIRONMENTAL")),
        ]
        for kind, keywords in mapping:
            if isinstance(keywords, str):
                if keywords in t:
                    return kind
            else:
                for kw in keywords:
                    if kw in t:
                        return kind
        return FilingKind.OTHER

    def fetch(self, ref: FilingRef) -> Optional[Filing]:
        if not ref.url:
            return None
        try:
            headers = {"Referer": f"{API_BASE}/search/titlesearch.xhtml"}
            resp = http_get(ref.url, headers=headers)
            return Filing(ref=ref, content=resp.content)
        except Exception:
            return None

    def close(self):
        if self._registry:
            self._registry.close()
            self._registry = None
