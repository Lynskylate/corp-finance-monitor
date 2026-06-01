"""
End-to-end tests for the fully deployed stack (Phase 3E).

Tests the running docker-compose services via nginx (127.0.0.1:8080).
The same paths are exposed over Tailscale at https://gtr.tail414c32.ts.net.

Prerequisites:
    docker compose up -d   (backend + frontend + nginx)

Run:
    python3 -m unittest tests/test_e2e_deployed.py -v

If you want to test the tailnet HTTPS endpoint instead of localhost,
set BASE_URL env var:
    BASE_URL=https://gtr.tail414c32.ts.net python3 -m unittest tests/test_e2e_deployed.py -v
"""
import json
import os
import unittest
import urllib.request
from urllib.error import HTTPError, URLError

DEFAULT_BASE = "http://127.0.0.1:8080"
BASE = os.environ.get("BASE_URL", DEFAULT_BASE).rstrip("/")

TIMEOUT = 15.0


def _http(url: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body
    except HTTPError as e:
        body = e.read()
        return e.code, dict(e.headers), body


def _json(status: int, headers: dict, body: bytes):
    try:
        return status, headers, json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return status, headers, body.decode("utf-8")


class TestDeployedHealthAndAPI(unittest.TestCase):
    """Backend API smoke against the running compose stack."""

    def test_healthz(self):
        status, headers, body = _json(*_http(BASE + "/healthz"))
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})

    def test_api_filings_list(self):
        status, headers, body = _json(*_http(BASE + "/api/filings"))
        self.assertEqual(status, 200)
        self.assertIn("items", body)
        self.assertIn("total", body)
        self.assertIsInstance(body["items"], list)
        self.assertIsInstance(body["total"], int)

    def test_api_filings_detail_404(self):
        status, _, _ = _http(BASE + "/api/filings/sse/does-not-exist")
        self.assertEqual(status, 404)

    def test_api_filings_with_source_filter(self):
        # The deployed instance may have real data; we just assert the
        # endpoint accepts the source query param and returns JSON.
        status, headers, body = _json(*_http(BASE + "/api/filings?source=sse"))
        self.assertEqual(status, 200)
        self.assertIn("items", body)

    def test_api_filings_with_limit_offset(self):
        status, headers, body = _json(*_http(BASE + "/api/filings?limit=5&offset=0"))
        self.assertEqual(status, 200)
        self.assertIn("items", body)
        self.assertIn("limit", body)
        self.assertIn("offset", body)
        self.assertEqual(body.get("limit"), 5)
        self.assertEqual(body.get("offset"), 0)

    def test_api_unknown_route_404(self):
        status, _, _ = _http(BASE + "/api/unknown")
        self.assertEqual(status, 404)


class TestDeployedCORSHeaders(unittest.TestCase):
    """CORS headers must be present on API responses (Phase 3A requirement)."""

    def test_cors_on_api_filings(self):
        # CORSMiddleware only adds the header when Origin is present.
        req = urllib.request.Request(
            BASE + "/api/filings",
            headers={"Origin": "https://example.com"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            headers = dict(resp.headers)
        self.assertIn("access-control-allow-origin", {k.lower() for k in headers})

    def test_cors_preflight_options(self):
        req = urllib.request.Request(
            BASE + "/api/filings",
            method="OPTIONS",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                headers = dict(resp.headers)
        except HTTPError as e:
            headers = dict(e.headers)

        hdr_keys = {k.lower() for k in headers}
        self.assertIn("access-control-allow-origin", hdr_keys)
        self.assertIn("access-control-allow-methods", hdr_keys)


class TestDeployedFrontend(unittest.TestCase):
    """Frontend static assets served by nginx."""

    def test_root_returns_html(self):
        status, headers, body = _http(BASE + "/")
        self.assertEqual(status, 200)
        content_type = headers.get("Content-Type", "").lower()
        self.assertIn("text/html", content_type)
        html = body.decode("utf-8")
        self.assertIn("<title>corp-finance-monitor</title>", html)
        self.assertIn('id="root"', html)

    def test_js_asset_exists(self):
        # Parse the HTML to find the JS bundle URL, then fetch it.
        status, _, body = _http(BASE + "/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")

        # Find script src like /assets/index-*.js
        import re
        m = re.search(r'src="(/assets/[^"]+\.js)"', html)
        self.assertIsNotNone(m, "no JS bundle found in HTML")
        js_url = BASE + m.group(1)

        status, headers, body = _http(js_url)
        self.assertEqual(status, 200)
        content_type = headers.get("Content-Type", "").lower()
        self.assertIn("javascript", content_type or "application/javascript")
        self.assertGreater(len(body), 1000, "JS bundle suspiciously small")

    def test_css_asset_exists(self):
        status, _, body = _http(BASE + "/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")

        import re
        m = re.search(r'href="(/assets/[^"]+\.css)"', html)
        self.assertIsNotNone(m, "no CSS bundle found in HTML")
        css_url = BASE + m.group(1)

        status, headers, body = _http(css_url)
        self.assertEqual(status, 200)
        content_type = headers.get("Content-Type", "").lower()
        self.assertIn("css", content_type)
        self.assertGreater(len(body), 100, "CSS bundle suspiciously small")

    def test_spa_routing_fallback(self):
        # Any unknown path should return index.html (SPA routing).
        status, headers, body = _http(BASE + "/filings/sse/12345")
        self.assertEqual(status, 200)
        content_type = headers.get("Content-Type", "").lower()
        self.assertIn("text/html", content_type)
        html = body.decode("utf-8")
        self.assertIn("<title>corp-finance-monitor</title>", html)


class TestDeployedTailnetAccessibilityNote(unittest.TestCase):
    """
    This test documents how to verify the tailnet endpoint.
    It does not run automatically because DNS resolution of the
    tailnet domain requires the test runner to be on the same tailnet.
    """

    @unittest.skipUnless(
        os.environ.get("BASE_URL", "").startswith("https://"),
        "tailnet HTTPS verification requires BASE_URL to be set to tailnet domain",
    )
    def test_https_healthz_via_tailnet(self):
        status, headers, body = _json(*_http(BASE + "/healthz"))
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})


if __name__ == "__main__":
    unittest.main()
