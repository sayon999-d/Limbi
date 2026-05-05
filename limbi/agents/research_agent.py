

from __future__ import annotations

import hashlib
import logging
import re
import time
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
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A 'query' is required")

        results = self._simulate_search(query, num_results)

        return {
            "message": f"Found {len(results)} results for '{query}'",
            "query": query,
            "results": results,
            "search_engine": "simulated",
            "note": "Configure SEARCH_API_KEY for live search results",
        }

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

    def _simulate_search(self, query: str, num_results: int) -> list[dict[str, str]]:

        return [
            {
                "title": f"Result {i+1}: {query}",
                "url": f"https://example.com/search/{query.replace(' ', '-')}/{i+1}",
                "snippet": f"Simulated search result {i+1} for '{query}'. Configure SEARCH_API_KEY for live results.",
            }
            for i in range(num_results)
        ]

    def _html_to_text(self, html: str) -> str:

        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r'<[^>]+>', ' ', text)

        text = re.sub(r'\s+', ' ', text).strip()
        return text
