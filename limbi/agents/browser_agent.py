from __future__ import annotations
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from . import BaseAgent
from limbi.permissions import require_permission
from limbi.workspace import load_config

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
                "click_selector",
                "fill_form",
                "summarize_page",
                "check_status",
            ],
        }

    def _require_network_access(self, action: str) -> None:
        config = load_config()
        require_permission(config, "network", self.agent_name, action)

    def _load_page_document(self, method: str, url: str, timeout_sec: int) -> dict[str, Any] | None:
        rendered = self._render_page(url, timeout_sec)
        if rendered:
            rendered["source_method"] = "playwright"
            rendered["request_method"] = method
            return rendered

        resp, error = self._request(method, url, timeout_sec)
        if error or resp is None:
            return None

        return {
            "source_method": "httpx",
            "request_method": method,
            "final_url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "html": resp.text,
            "title": self._extract_title(resp.text),
        }

    def _render_page(self, url: str, timeout_sec: int) -> dict[str, Any] | None:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            logger.debug("Playwright unavailable for browser render: %s", exc)
            return None

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
                html = page.content()
                result = {
                    "final_url": page.url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "html": html,
                    "title": page.title(),
                }
                context.close()
                browser.close()
                return result
        except PlaywrightTimeoutError as exc:
            logger.debug("Playwright timed out for %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.debug("Playwright render failed for %s: %s", url, exc)
            return None

    def handle_fetch_page(self, url: str = "", timeout_sec: int = 10, **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("fetch_page")

        document = self._load_page_document("GET", url, timeout_sec)
        if not document:
            return {
                "message": f"[SIMULATED] Unable to fetch {url}",
                "url": url,
                "status_code": None,
                "content_type": "",
                "title": "",
                "text_preview": "Network unavailable or blocked by policy.",
                "truncated": False,
                "error": "Unable to fetch page",
            }

        text = self._html_to_text(document.get("html", ""))
        page_text = text
        return {
            "message": f"Fetched {url}",
            "url": document.get("final_url") or url,
            "status_code": document.get("status_code"),
            "content_type": document.get("content_type", ""),
            "title": document.get("title", ""),
            "source_method": document.get("source_method", "httpx"),
            "text_preview": page_text[:1200],
            "truncated": len(page_text) > 1200,
        }

    def handle_extract_links(self, url: str = "", limit: int = 25, **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("extract_links")

        document = self._load_page_document("GET", url, 10)
        if not document:
            return {
                "message": f"[SIMULATED] Unable to inspect links for {url}",
                "url": url,
                "domain": urlparse(url).netloc,
                "links": [],
                "total_links": 0,
                "error": "Unable to inspect links",
            }

        html = document.get("html", "")
        links = []
        for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            full_url = urljoin(str(document.get("final_url") or url), unescape(href).strip())
            text = self._html_to_text(label).strip()
            links.append({"url": full_url, "label": text[:120] or "(no label)"})

        return {
            "message": f"Extracted {min(len(links), limit)} links",
            "url": str(document.get("final_url") or url),
            "domain": urlparse(str(document.get("final_url") or url)).netloc,
            "source_method": document.get("source_method", "httpx"),
            "links": links[:limit],
            "total_links": len(links),
        }

    def handle_inspect_forms(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("inspect_forms")

        document = self._load_page_document("GET", url, 10)
        if not document:
            return {
                "message": f"[SIMULATED] Unable to inspect forms for {url}",
                "url": url,
                "forms": [],
                "error": "Unable to inspect forms",
            }

        html = document.get("html", "")
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
                "action": urljoin(str(document.get("final_url") or url), action) if action else str(document.get("final_url") or url),
                "method": method,
                "inputs": inputs,
            })

        return {
            "message": f"Found {len(forms)} forms",
            "url": str(document.get("final_url") or url),
            "source_method": document.get("source_method", "httpx"),
            "forms": forms,
        }

    def handle_summarize_page(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("summarize_page")

        document = self._load_page_document("GET", url, 10)
        if not document:
            return {
                "message": f"[SIMULATED] Unable to summarize {url}",
                "title": "",
                "section_headings": [],
                "word_count": 0,
                "summary": "",
                "error": "Unable to summarize page",
            }

        html = document.get("html", "")
        page_text = self._html_to_text(html)
        headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.I | re.S)
        sections = [self._html_to_text(h).strip() for h in headings if self._html_to_text(h).strip()]
        words = page_text.split()
        return {
            "message": f"Summarized page {str(document.get('final_url') or url)}",
            "title": document.get("title", self._extract_title(html)),
            "section_headings": sections[:12],
            "word_count": len(words),
            "summary": " ".join(words[:120]),
            "source_method": document.get("source_method", "httpx"),
        }

    def handle_check_status(self, url: str = "", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("check_status")

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

    def handle_click_selector(self, url: str = "", selector: str = "", timeout_sec: int = 10, **kw: Any) -> dict[str, Any]:
        if not url or not selector:
            raise ValueError("Both 'url' and 'selector' are required")

        self._require_network_access("click_selector")

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "message": f"[SIMULATED] Unable to click {selector} on {url}",
                "url": url,
                "selector": selector,
                "error": f"Playwright unavailable: {exc}",
                "source_method": "httpx",
            }

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
                page.click(selector, timeout=timeout_sec * 1000)
                html = page.content()
                result = {
                    "message": f"Clicked {selector} on {url}",
                    "url": page.url,
                    "title": page.title(),
                    "content_type": "text/html",
                    "status_code": 200,
                    "source_method": "playwright",
                    "text_preview": self._html_to_text(html)[:1200],
                    "truncated": len(html) > 1200,
                }
                context.close()
                browser.close()
                return result
        except PlaywrightTimeoutError as exc:
            return {"message": f"Timed out clicking {selector} on {url}", "url": url, "selector": selector, "error": str(exc), "source_method": "playwright"}
        except Exception as exc:
            return {"message": f"Failed to click {selector} on {url}", "url": url, "selector": selector, "error": str(exc), "source_method": "playwright"}

    def handle_fill_form(
        self,
        url: str = "",
        fields: dict[str, str] | None = None,
        submit_selector: str = "",
        timeout_sec: int = 10,
        **kw: Any,
    ) -> dict[str, Any]:
        if not url:
            raise ValueError("A 'url' is required")

        self._require_network_access("fill_form")
        fields = fields or {}

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "message": f"[SIMULATED] Unable to fill form on {url}",
                "url": url,
                "fields": fields,
                "error": f"Playwright unavailable: {exc}",
                "source_method": "httpx",
            }

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
                for selector, value in fields.items():
                    page.locator(selector).fill(str(value))
                if submit_selector:
                    page.click(submit_selector, timeout=timeout_sec * 1000)
                else:
                    page.keyboard.press("Enter")
                html = page.content()
                result = {
                    "message": f"Filled form on {url}",
                    "url": page.url,
                    "title": page.title(),
                    "content_type": "text/html",
                    "status_code": 200,
                    "source_method": "playwright",
                    "filled_fields": list(fields.keys()),
                    "submit_selector": submit_selector,
                    "text_preview": self._html_to_text(html)[:1200],
                    "truncated": len(html) > 1200,
                }
                context.close()
                browser.close()
                return result
        except PlaywrightTimeoutError as exc:
            return {"message": f"Timed out filling form on {url}", "url": url, "fields": fields, "error": str(exc), "source_method": "playwright"}
        except Exception as exc:
            return {"message": f"Failed to fill form on {url}", "url": url, "fields": fields, "error": str(exc), "source_method": "playwright"}

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
