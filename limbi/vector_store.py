

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("limbi.vectorstore")

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".c", ".cpp", ".h",
    ".css", ".html", ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".sh", ".sql", ".dockerfile",
}

_SPLIT_PATTERNS: dict[str, re.Pattern] = {
    ".py": re.compile(r"^(?=(?:class |def |async def ))", re.MULTILINE),
    ".js": re.compile(r"^(?=(?:function |class |const \w+ = (?:async )?\(|export ))", re.MULTILINE),
    ".ts": re.compile(r"^(?=(?:function |class |interface |type |const \w+ = |export ))", re.MULTILINE),
    ".go": re.compile(r"^(?=(?:func |type ))", re.MULTILINE),
    ".rs": re.compile(r"^(?=(?:fn |struct |impl |enum |trait |pub ))", re.MULTILINE),
    ".java": re.compile(r"^(?=(?:public |private |protected |class |interface ))", re.MULTILINE),
    ".rb": re.compile(r"^(?=(?:class |module |def ))", re.MULTILINE),
    ".md": re.compile(r"^(?=#{1,3} )", re.MULTILINE),
}

RELEVANCE_THRESHOLD = 1.2
CHROMADB_INSTALL_MESSAGE = (
    "ChromaDB is not installed. Codebase RAG is optional; install it with "
    '`pip install "limbi[rag]"` to use vector search and codebase ingestion.'
)

class VectorStore:

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "limbi_docs",
    ) -> None:
        self._persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        self._collection_name = collection_name
        self._client = None
        self._collection = None

        self._content_hashes: dict[str, str] = {}

    def _workspace_root(self) -> Path:
        return Path(
            os.getenv("LIMBI_WORKSPACE_ROOT")
            or os.getenv("WORKSPACE_ROOT")
            or Path.cwd()
        ).expanduser().resolve()

    def _ensure_within_workspace(self, directory: Path) -> Path:
        allow_outside = os.getenv("LIMBI_ALLOW_OUTSIDE_WORKSPACE", "").strip().lower() in ("1", "true", "yes", "on")
        workspace_root = self._workspace_root()
        resolved = directory.expanduser().resolve()
        if allow_outside or resolved == workspace_root or workspace_root in resolved.parents:
            return resolved
        raise PermissionError(f"Directory '{resolved}' is outside the workspace root '{workspace_root}'")

    def _ensure_ready(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "ChromaDB ready - collection '%s' (%d docs)",
                self._collection_name,
                self._collection.count(),
            )
        except ImportError as exc:
            raise RuntimeError(CHROMADB_INSTALL_MESSAGE) from exc

    def ingest_directory(
        self,
        directory: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> dict[str, Any]:

        self._ensure_ready()
        assert self._collection is not None

        dir_path = self._ensure_within_workspace(Path(directory))
        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {dir_path}")

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []
        files_processed = 0
        files_skipped = 0

        for filepath in dir_path.rglob("*"):
            if not filepath.is_file():
                continue
            if filepath.suffix.lower() not in _CODE_EXTENSIONS:
                continue

            rel = str(filepath.relative_to(dir_path))
            if any(
                part.startswith(".") or part in ("node_modules", "venv", "__pycache__", "chroma_db")
                for part in filepath.parts
            ):
                continue

            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            if self._content_hashes.get(rel) == content_hash:
                files_skipped += 1
                continue
            self._content_hashes[rel] = content_hash

            ext = filepath.suffix.lower()
            chunks = _smart_chunk(text, ext, chunk_size, chunk_overlap)

            for i, chunk_info in enumerate(chunks):
                doc_id = hashlib.sha256(f"{rel}::{i}::{content_hash}".encode()).hexdigest()[:16]
                documents.append(chunk_info["text"])
                metadatas.append({
                    "source": rel,
                    "chunk_index": str(i),
                    "language": ext.lstrip("."),
                    "start_line": str(chunk_info.get("start_line", 0)),
                    "symbol": chunk_info.get("symbol", ""),
                    "content_hash": content_hash,
                })
                ids.append(doc_id)

            files_processed += 1

        if documents:

            for start in range(0, len(documents), 500):
                end = start + 500
                self._collection.upsert(
                    documents=documents[start:end],
                    metadatas=metadatas[start:end],
                    ids=ids[start:end],
                )

        logger.info(
            "Ingested %d chunks from %d files (%d skipped unchanged) in %s",
            len(documents), files_processed, files_skipped, directory,
        )
        return {
            "directory": str(dir_path),
            "files_processed": files_processed,
            "files_skipped_unchanged": files_skipped,
            "chunks_indexed": len(documents),
            "total_in_collection": self._collection.count(),
        }

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        relevance_threshold: float = RELEVANCE_THRESHOLD,
    ) -> list[dict[str, Any]]:

        self._ensure_ready()
        assert self._collection is not None

        if self._collection.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self._collection.count()),
        )

        docs: list[dict[str, Any]] = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i] if results["distances"] else None

            if distance is not None and distance > relevance_threshold:
                continue
            docs.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": distance,
                "relevance_score": round(1 - (distance or 0), 3),
            })
        return docs

    def get_context_string(self, query: str, n_results: int = 3) -> str:

        try:
            docs = self.query(query, n_results)
        except RuntimeError as exc:
            if str(exc) != CHROMADB_INSTALL_MESSAGE:
                logger.debug("Vector store unavailable: %s", exc)
            return ""
        except Exception as exc:
            logger.debug("Vector store query failed: %s", exc)
            return ""
        if not docs:
            return ""

        parts = ["## Retrieved Context from Local Codebase"]
        for doc in docs:
            source = doc.get("metadata", {}).get("source", "unknown")
            lang = doc.get("metadata", {}).get("language", "")
            symbol = doc.get("metadata", {}).get("symbol", "")
            score = doc.get("relevance_score", "?")
            header = f"--- {source}"
            if symbol:
                header += f" ({symbol})"
            header += f" [relevance: {score}] ---"
            parts.append(f"\n{header}")
            parts.append(f"```{lang}\n{doc['content']}\n```")
        return "\n".join(parts)

    def stats(self) -> dict[str, Any]:

        try:
            self._ensure_ready()
            assert self._collection is not None
            return {
                "collection": self._collection_name,
                "document_count": self._collection.count(),
                "persist_dir": self._persist_dir,
                "tracked_files": len(self._content_hashes),
                "available": True,
            }
        except Exception as exc:
            return {"error": str(exc), "available": False}

    def delete_collection(self) -> dict[str, str]:

        self._ensure_ready()
        if self._client and self._collection:
            self._client.delete_collection(self._collection_name)
            self._collection = None
            self._content_hashes.clear()
            return {"message": f"Collection '{self._collection_name}' deleted"}
        return {"message": "No collection to delete"}

def _smart_chunk(
    text: str,
    ext: str,
    max_chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:

    pattern = _SPLIT_PATTERNS.get(ext)

    if pattern:
        return _chunk_by_pattern(text, pattern, max_chunk_size)
    else:
        return _chunk_by_lines(text, max_chunk_size, overlap)

def _chunk_by_pattern(
    text: str,
    pattern: re.Pattern,
    max_chunk_size: int,
) -> list[dict[str, Any]]:

    parts = pattern.split(text)
    chunks: list[dict[str, Any]] = []
    current_line = 1

    for part in parts:
        if not part.strip():
            current_line += part.count("\n")
            continue

        first_line = part.split("\n", 1)[0].strip()
        symbol = _extract_symbol_name(first_line)

        if len(part) <= max_chunk_size:
            chunks.append({
                "text": part.strip(),
                "start_line": current_line,
                "symbol": symbol,
            })
        else:

            sub_chunks = _chunk_by_lines(part, max_chunk_size, overlap=100)
            for sc in sub_chunks:
                sc["symbol"] = symbol
                sc["start_line"] = current_line + sc.get("start_line", 0)
            chunks.extend(sub_chunks)

        current_line += part.count("\n")

    return chunks

def _chunk_by_lines(
    text: str,
    max_size: int,
    overlap: int,
) -> list[dict[str, Any]]:

    lines = text.split("\n")
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_size = 0
    start_line = 0

    for i, line in enumerate(lines):
        line_size = len(line) + 1
        if current_size + line_size > max_size and current:
            chunks.append({
                "text": "\n".join(current),
                "start_line": start_line,
                "symbol": "",
            })

            overlap_lines = max(1, overlap // max(1, max_size // max(len(current), 1)))
            current = current[-overlap_lines:]
            current_size = sum(len(l) + 1 for l in current)
            start_line = max(0, i - len(current))
        current.append(line)
        current_size += line_size

    if current:
        chunks.append({
            "text": "\n".join(current),
            "start_line": start_line,
            "symbol": "",
        })

    return chunks

def _extract_symbol_name(first_line: str) -> str:

    m = re.match(r"(?:async )?(?:def|class)\s+(\w+)", first_line)
    if m:
        return m.group(1)

    m = re.match(r"(?:export\s+)?(?:function\s+(\w+)|const\s+(\w+))", first_line)
    if m:
        return m.group(1) or m.group(2) or ""

    m = re.match(r"(?:func|type)\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", first_line)
    if m:
        return m.group(1)
    return ""
