

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import BaseAgent

class KnowledgeAgent(BaseAgent):

    agent_name = "knowledge_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "knowledge",
            "status": "ready",
            "capabilities": [
                "build_knowledge_map",
                "answer_from_notes",
                "extract_entities",
                "deduplicate_notes",
                "suggest_gaps",
            ],
        }

    def handle_build_knowledge_map(self, notes: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        notes = notes or []
        entities = Counter()
        for note in notes:
            for token in re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", note):
                entities[token] += 1
        nodes = [{"name": name, "mentions": count} for name, count in entities.most_common(15)]
        return {"message": "Built knowledge map", "nodes": nodes}

    def handle_answer_from_notes(self, question: str = "", notes: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not question:
            raise ValueError("'question' is required")
        notes = notes or []
        relevant = [note for note in notes if any(word.lower() in note.lower() for word in question.split()[:5])]
        return {"message": "Answered from notes", "answer": relevant[:3], "matches": len(relevant)}

    def handle_extract_entities(self, text: str = "", **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        entities = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", text)
        return {"message": "Extracted entities", "entities": sorted(set(entities))}

    def handle_deduplicate_notes(self, notes: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        notes = notes or []
        unique = list(dict.fromkeys(note.strip() for note in notes if note.strip()))
        return {"message": "Deduplicated notes", "original": len(notes), "unique": len(unique), "notes": unique}

    def handle_suggest_gaps(self, notes: list[str] | None = None, topic: str = "", **kw: Any) -> dict[str, Any]:
        notes = notes or []
        joined = " ".join(notes).lower()
        gaps = []
        for expected in ["owner", "deadline", "decision", "risk"]:
            if expected not in joined:
                gaps.append(expected)
        return {"message": f"Suggested knowledge gaps for {topic or 'notes'}", "gaps": gaps}
