from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.nlp")


class NLPAgent(BaseAgent):

    agent_name = "nlp_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "nlp", "status": "ready", "capabilities": ["sentiment_analysis", "summarize_text", "extract_entities", "translate", "classify_intent"]}

    def handle_sentiment_analysis(self, text: str = "", **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        positive = ["good", "great", "excellent", "love", "best", "amazing", "happy", "wonderful", "fantastic"]
        negative = ["bad", "terrible", "worst", "hate", "awful", "horrible", "sad", "angry", "poor"]
        words = text.lower().split()
        pos_count = sum(1 for w in words if w in positive)
        neg_count = sum(1 for w in words if w in negative)
        total = pos_count + neg_count or 1
        score = (pos_count - neg_count) / total
        label = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"
        return {"message": f"Sentiment: {label}", "sentiment": label, "score": round(score, 3), "confidence": round(abs(score), 2), "word_count": len(words)}

    def handle_summarize_text(self, text: str = "", max_sentences: int = 3, **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        summary = ". ".join(sentences[:max_sentences]) + "." if sentences else text
        return {"message": "Text summarized", "summary": summary, "original_sentences": len(sentences), "summary_sentences": min(len(sentences), max_sentences), "compression_ratio": round(len(summary) / max(len(text), 1), 2)}

    def handle_extract_entities(self, text: str = "", **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        import re
        entities: list[dict[str, str]] = []
        emails = re.findall(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', text)
        for e in emails:
            entities.append({"type": "EMAIL", "value": e})
        urls = re.findall(r'https?://\S+', text)
        for u in urls:
            entities.append({"type": "URL", "value": u})
        dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)
        for d in dates:
            entities.append({"type": "DATE", "value": d})
        numbers = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
        for n in numbers:
            entities.append({"type": "CURRENCY", "value": n})
        caps = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
        for c in set(caps):
            entities.append({"type": "PERSON_OR_ORG", "value": c})
        return {"message": f"Extracted {len(entities)} entities", "entities": entities, "entity_count": len(entities)}

    def handle_translate(self, text: str = "", source_lang: str = "auto", target_lang: str = "en", **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        return {"message": f"[SIMULATED] Translation {source_lang} -> {target_lang}", "original": text, "translated": text, "source_lang": source_lang, "target_lang": target_lang, "note": "Connect a translation API for live translation"}

    def handle_classify_intent(self, text: str = "", intents: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        intents = intents or ["question", "command", "complaint", "feedback", "greeting"]
        lower = text.lower()
        if "?" in text or lower.startswith(("what", "how", "why", "when", "where", "who", "can", "is")):
            matched = "question"
        elif lower.startswith(("please", "create", "make", "build", "deploy", "run", "delete", "update")):
            matched = "command"
        elif any(w in lower for w in ["bad", "broken", "issue", "bug", "wrong"]):
            matched = "complaint"
        elif any(w in lower for w in ["hi", "hello", "hey", "good morning"]):
            matched = "greeting"
        else:
            matched = "feedback"
        return {"message": f"Intent classified: {matched}", "intent": matched, "text": text[:100], "available_intents": intents}
