

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from agents import BaseAgent

class MultimodalAgent(BaseAgent):

    agent_name = "multimodal_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "multimodal",
            "status": "ready",
            "capabilities": [
                "inspect_asset",
                "analyze_document_text",
                "generate_alt_text",
                "create_processing_plan",
                "extract_media_metadata",
            ],
        }

    def handle_inspect_asset(self, path: str = "", **kw: Any) -> dict[str, Any]:
        if not path:
            raise ValueError("'path' is required")
        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"Asset '{path}' does not exist")
        mime, _ = mimetypes.guess_type(target.name)
        stat = target.stat()
        return {
            "message": f"Inspected asset {target.name}",
            "path": str(target),
            "mime_type": mime or "application/octet-stream",
            "size_bytes": stat.st_size,
            "suffix": target.suffix.lower(),
        }

    def handle_analyze_document_text(self, text: str = "", **kw: Any) -> dict[str, Any]:
        if not text:
            raise ValueError("'text' is required")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headings = [line for line in lines if len(line.split()) <= 8 and line == line.title()]
        return {
            "message": "Analyzed document text",
            "line_count": len(lines),
            "headings": headings[:10],
            "summary": " ".join(" ".join(lines).split()[:120]),
        }

    def handle_generate_alt_text(self, filename: str = "", context: str = "", **kw: Any) -> dict[str, Any]:
        if not filename:
            raise ValueError("'filename' is required")
        basename = Path(filename).stem.replace("-", " ").replace("_", " ")
        alt = f"Image related to {basename}".strip()
        if context:
            alt += f", shown in the context of {context}"
        return {"message": "Generated alt text", "alt_text": alt}

    def handle_create_processing_plan(self, asset_type: str = "", goal: str = "", **kw: Any) -> dict[str, Any]:
        if not asset_type or not goal:
            raise ValueError("'asset_type' and 'goal' are required")
        steps = [
            "ingest asset metadata",
            "select modality-specific parser",
            f"extract features needed for {goal}",
            "store normalized result and confidence notes",
        ]
        return {"message": f"Created processing plan for {asset_type}", "steps": steps}

    def handle_extract_media_metadata(self, path: str = "", **kw: Any) -> dict[str, Any]:
        if not path:
            raise ValueError("'path' is required")
        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"Asset '{path}' does not exist")
        mime, _ = mimetypes.guess_type(target.name)
        return {
            "message": "Extracted media metadata",
            "name": target.name,
            "mime_type": mime or "application/octet-stream",
            "extension": target.suffix.lower(),
        }
