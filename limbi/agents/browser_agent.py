from __future__ import annotations
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from . import BaseAgent

logger = logging.getLogger("limbi.agents.browser")

class BrowserAgent(BaseAgent):

    agent_name = "browser_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "browser_inspection",
            "status": "ready",
            "capabilities": [
                "fetch_page",
                "extract_links",
                "inspect_forms",
                "summarize_page",
                "check_status",
            ],
        }

    def handle_fetch_page(self, url: str = "", timeout_sec: int = 10, **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        resp, error = self._request("GET", url, timeout_sec)
        if error:
            return {
                "message": f"[SIMULATED] Unable to fetch {url}",
                "url": url,
                "status_code": None,
                "content_type": "",
                "title": "",
                "text_preview": f"Network unavailable: {error}",
                "truncated": False,
                "error": error,
            }

        text = resp.text
        page_text = self._html_to_text(text)
        return {
            "message": f"Fetched {url}",
            "url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "title": self._extract_title(text),
            "text_preview": page_text[:1200],
            "truncated": len(page_text) > 1200,
        }

    def handle_extract_links(self, url: str = "", limit: int = 25, **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        resp, error = self._request("GET", url, 10)
        if error:
            return {
                "message": f"[SIMULATED] Unable to inspect links for {url}",
                "url": url,
                "domain": urlparse(url).netloc,
                "links": [],
                "total_links": 0,
                "error": error,
            }

        html = resp.text
        links = []
        for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            full_url = urljoin(str(resp.url), unescape(href).strip())
            text = self._html_to_text(label).strip()
            links.append({"url": full_url, "label": text[:120] or "(no label)"})

        return {
            "message": f"Extracted {min(len(links), limit)} links",
            "url": str(resp.url),
            "domain": urlparse(str(resp.url)).netloc,
            "links": links[:limit],
            "total_links": len(links),
        }

    def handle_inspect_forms(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        resp, error = self._request("GET", url, 10)
        if error:
            return {
                "message": f"[SIMULATED] Unable to inspect forms for {url}",
                "url": url,
                "forms": [],
                "error": error,
            }

        html = resp.text
        forms = []
        for idx, form_html in enumerate(re.findall(r"<form\b.*?</form>", html, re.I | re.S), start=1):
            action = self._extract_attr(form_html, "action")
            method = (self._extract_attr(form_html, "method") or "GET").upper()
            inputs = []
            for input_html in re.findall(r"<input\b[^>]*>", form_html, re.I | re.S):
                inputs.append({
                    "name": self._extract_attr(input_html, "name"),
                    "type": self._extract_attr(input_html, "type") or "text",
                })
            forms.append({
                "form_index": idx,
                "action": urljoin(str(resp.url), action) if action else str(resp.url),
                "method": method,
                "inputs": inputs,
            })

        return {
            "message": f"Found {len(forms)} forms",
            "url": str(resp.url),
            "forms": forms,
        }

    def handle_summarize_page(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        resp, error = self._request("GET", url, 10)
        if error:
            return {
                "message": f"[SIMULATED] Unable to summarize {url}",
                "title": "",
                "section_headings": [],
                "word_count": 0,
                "summary": "",
                "error": error,
            }

        html = resp.text
        page_text = self._html_to_text(html)
        headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.I | re.S)
        sections = [self._html_to_text(h).strip() for h in headings if self._html_to_text(h).strip()]
        words = page_text.split()
        return {
            "message": f"Summarized page {str(resp.url)}",
            "title": self._extract_title(html),
            "section_headings": sections[:12],
            "word_count": len(words),
            "summary": " ".join(words[:120]),
        }

    def handle_check_status(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        resp, error = self._request("HEAD", url, 10)
        if error:
            return {
                "message": f"[SIMULATED] Unable to check status for {url}",
                "url": url,
                "status_code": None,
                "ok": False,
                "headers": {},
                "error": error,
            }

        return {
            "message": f"Status checked for {url}",
            "url": str(resp.url),
            "status_code": resp.status_code,
            "ok": resp.status_code < 400,
            "headers": {
                "content_type": resp.headers.get("content-type", ""),
                "content_length": resp.headers.get("content-length", ""),
                "server": resp.headers.get("server", ""),
            },
        }

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        return self._html_to_text(match.group(1)).strip() if match else ""

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_attr(self, html: str, name: str) -> str:
        match = re.search(rf'{name}=["\']([^"\']+)["\']', html, re.I)
        return unescape(match.group(1)).strip() if match else ""

    def _request(self, method: str, url: str, timeout_sec: int):
        import httpx

        try:
            with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
                response = client.request(method, url, headers={"User-Agent": "StepWise-AI/2.0"})
            return response, ""
        except Exception as exc:
            logger.warning("Browser agent request failed for %s %s: %s", method, url, exc)
            return None, str(exc)
