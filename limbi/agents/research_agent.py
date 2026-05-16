

from __future__ import annotations

import hashlib
import logging
import re
import time
from urllib.parse import quote_plus
from typing import Any
from urllib.parse import urlparse

from . import BaseAgent

logger = logging.getLogger("limbi.agents.research")

_url_cache: dict[str, dict[str, Any]] = {}

class ResearchAgent(BaseAgent):

    agent_name = "research_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "research_web",
            "status": "ready",
            "cached_urls": len(_url_cache),
            "capabilities": [
                "web_search", "fetch_url", "summarize",
                "fact_check", "compare_sources",
            ],
        }

    def handle_web_search(
        self,
        query: str = "",
        num_results: int = 5,
        engine: str = "auto",
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            query = str(
                kw.get("topic")
                or kw.get("search")
                or kw.get("subject")
                or kw.get("question")
                or ""
            ).strip()
        if not query:
            raise ValueError("A 'query' is required")

        results, search_engine = self._search_web(query, num_results=num_results, engine=engine)

        return {
            "message": f"Found {len(results)} results for '{query}'",
            "query": query,
            "results": results,
            "search_engine": search_engine,
            "note": "Live web search used best-effort public search endpoints",
        }

    def handle_find_information(
        self,
        query: str = "",
        num_results: int = 5,
        **kw: Any,
    ) -> dict[str, Any]:
        return self.handle_web_search(query=query, num_results=num_results, **kw)

    def handle_fetch_url(
        self,
        url: str = "",
        extract_text: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        if not url:
            raise ValueError("A 'url' is required")

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}")

        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in _url_cache:
            cached = _url_cache[cache_key]
            cached["from_cache"] = True
            return cached

        try:
            import httpx

            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "StepWise-AI/2.0"})
                resp.raise_for_status()

                content = resp.text

                if extract_text and "text/html" in resp.headers.get("content-type", ""):
                    content = self._html_to_text(content)

                result = {
                    "message": f"Fetched {len(content)} chars from {parsed.netloc}",
                    "url": url,
                    "domain": parsed.netloc,
                    "status_code": resp.status_code,
                    "content_length": len(content),
                    "content": content[:5000],
                    "truncated": len(content) > 5000,
                    "from_cache": False,
                }
                _url_cache[cache_key] = result
                return result

        except Exception as exc:
            return {
                "message": f"[SIMULATED] Content from {url}",
                "url": url,
                "error": str(exc),
                "content": f"Could not fetch URL: {exc}. In production, configure httpx.",
                "from_cache": False,
            }

    def handle_summarize(
        self,
        text: str = "",
        max_points: int = 5,
        style: str = "bullet",
        **kw: Any,
    ) -> dict[str, Any]:

        if not text:
            raise ValueError("'text' content is required for summarization")

        word_count = len(text.split())
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip() and len(s.strip()) > 20]

        if style == "tldr":

            summary = sentences[0] if sentences else text[:200]
            return {
                "message": f"TL;DR of {word_count} words",
                "summary": summary,
                "original_word_count": word_count,
                "style": "tldr",
            }

        scored = []
        for i, sent in enumerate(sentences):
            score = 0
            score += len(sent.split()) * 0.1
            score += sum(1 for w in sent.split() if w[0].isupper()) * 0.3
            score += sum(1 for c in sent if c.isdigit()) * 0.2
            score -= i * 0.05
            scored.append((score, sent))

        scored.sort(reverse=True)
        top_sentences = [s for _, s in scored[:max_points]]

        if style == "paragraph":
            summary = ". ".join(top_sentences) + "."
        else:
            summary = "\n".join(f"- {s}" for s in top_sentences)

        compression = round(1 - len(summary.split()) / max(word_count, 1), 2)

        return {
            "message": f"Summarized {word_count} words into {max_points} points",
            "summary": summary,
            "key_points": top_sentences,
            "original_word_count": word_count,
            "summary_word_count": len(summary.split()),
            "compression_ratio": compression,
            "style": style,
        }

    def handle_fact_check(
        self,
        claim: str = "",
        context: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not claim:
            raise ValueError("A 'claim' is required")

        indicators: list[dict[str, Any]] = []
        confidence_penalty = 0.0

        absolutist = re.findall(r'\b(always|never|every|none|all|impossible|guaranteed)\b', claim, re.I)
        if absolutist:
            indicators.append({"type": "absolutist_language", "found": absolutist, "risk": "high"})
            confidence_penalty += 0.2

        numbers = re.findall(r'\b\d{4}\b|\b\d+\.?\d*%|\$\d+', claim)
        if numbers:
            indicators.append({"type": "specific_numbers", "found": numbers, "risk": "medium"})
            confidence_penalty += 0.1

        citations = re.findall(r'according to|research shows|studies indicate|experts say', claim, re.I)
        if citations:
            indicators.append({"type": "authority_claims", "found": citations, "risk": "medium"})
            confidence_penalty += 0.1

        grounding_score = 1.0
        if context:
            claim_words = set(w.lower() for w in claim.split() if len(w) > 4)
            context_words = set(w.lower() for w in context.split() if len(w) > 4)
            overlap = claim_words & context_words
            grounding_score = len(overlap) / max(len(claim_words), 1)

        overall = max(0, 1.0 - confidence_penalty) * grounding_score
        verdict = "likely_accurate" if overall > 0.7 else "uncertain" if overall > 0.4 else "needs_verification"

        return {
            "claim": claim,
            "verdict": verdict,
            "confidence": round(overall, 2),
            "indicators": indicators,
            "grounding_score": round(grounding_score, 2),
            "recommendation": "Accept" if verdict == "likely_accurate" else "Verify independently",
        }

    def handle_compare_sources(
        self,
        sources: list[dict[str, str]] | None = None,
        topic: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        sources = sources or []
        if len(sources) < 2:
            raise ValueError("At least 2 sources are needed for comparison")

        source_terms: list[set[str]] = []
        for src in sources:
            content = src.get("content", "")
            terms = set(w.lower() for w in content.split() if len(w) > 4)
            source_terms.append(terms)

        all_terms = set().union(*source_terms)
        common_terms = set.intersection(*source_terms) if source_terms else set()

        agreement_ratio = len(common_terms) / max(len(all_terms), 1)
        unique_per_source = [
            {"source": sources[i].get("title", f"Source {i+1}"), "unique_terms": len(terms - common_terms)}
            for i, terms in enumerate(source_terms)
        ]

        return {
            "message": f"Compared {len(sources)} sources on '{topic}'",
            "topic": topic,
            "agreement_ratio": round(agreement_ratio, 2),
            "common_themes": list(common_terms)[:20],
            "source_analysis": unique_per_source,
            "consensus": "strong" if agreement_ratio > 0.6 else "moderate" if agreement_ratio > 0.3 else "weak",
        }

    def _search_web(self, query: str, num_results: int, engine: str = "auto") -> tuple[list[dict[str, str]], str]:
        normalized = (engine or "auto").lower().strip()
        if normalized not in {"auto", "", "google", "duckduckgo", "ddg"}:
            normalized = "auto"

        engines = ["google", "duckduckgo"] if normalized in {"auto", ""} else [normalized]
        if "duckduckgo" in engines:
            engines.append("google")
        elif "google" in engines:
            engines.append("duckduckgo")

        for candidate in engines:
            try:
                if candidate == "google":
                    results = self._search_google(query, num_results)
                else:
                    results = self._search_duckduckgo(query, num_results)
                if results:
                    return results, candidate
            except Exception as exc:
                logger.debug("Search engine %s failed for %r: %s", candidate, query, exc)

        return self._simulate_search(query, num_results), "simulated"

    def _search_google(self, query: str, num_results: int) -> list[dict[str, str]]:
        import httpx

        url = f"https://www.google.com/search?hl=en&gl=us&num={max(1, num_results)}&q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Limbi/1.0; +https://github.com/sayon999-d/Limbi-)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in re.finditer(r'<a[^>]+href="/url\?q=([^"&]+)[^"]*"[^>]*>(.*?)</a>', html, re.I | re.S):
            url = match.group(1).split("&")[0]
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if not title or not url or url in seen:
                continue
            seen.add(url)
            results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= num_results:
                break
        return results

    def _search_duckduckgo(self, query: str, num_results: int) -> list[dict[str, str]]:
        import httpx

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Limbi/1.0; +https://github.com/sayon999-d/Limbi-)",
        }
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        results: list[dict[str, str]] = []
        for match in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
            html,
            re.I | re.S,
        ):
            url = re.sub(r"&amp;", "&", match.group(1)).strip()
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet_html = match.group(3) or ""
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
            if not title or not url:
                continue
            results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= num_results:
                break
        return results

    def _simulate_search(self, query: str, num_results: int) -> list[dict[str, str]]:

        return [
            {
                "title": f"Result {i+1}: {query}",
                "url": f"https://example.com/search/{query.replace(' ', '-')}/{i+1}",
                "snippet": f"Simulated search result {i+1} for '{query}'.",
            }
            for i in range(num_results)
        ]

    def _html_to_text(self, html: str) -> str:

        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r'<[^>]+>', ' ', text)

        text = re.sub(r'\s+', ' ', text).strip()
        return text
