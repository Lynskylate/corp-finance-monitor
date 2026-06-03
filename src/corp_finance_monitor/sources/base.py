"""HTTP工具函数和常量，供各source实现复用"""

import time
from datetime import datetime, timedelta, timezone

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

TIMEOUT = 30
MAX_RETRIES = 3
CN_TZ = timezone(timedelta(hours=8))


def http_get(url: str, headers: dict | None = None, **kwargs) -> requests.Response:
    h = {**HEADERS, **(headers or {})}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=h, timeout=TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
            else:
                raise


def http_post(url: str, data: dict, headers: dict | None = None, **kwargs) -> requests.Response:
    h = {**HEADERS, **(headers or {})}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=h, data=data, timeout=TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
            else:
                raise


def parse_timestamp(ts) -> str:
    """将多种时间戳格式转为 YYYY-MM-DD"""
    if ts is None:
        return ""
    s = str(ts).strip()
    if not s or s == "0":
        return ""
    if s.isdigit() and len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if s.isdigit() and len(s) > 10:
        return datetime.fromtimestamp(int(s) / 1000, tz=CN_TZ).strftime("%Y-%m-%d")
    return s[:10]
