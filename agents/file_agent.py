

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.file")

_CATEGORIES: dict[str, list[str]] = {
    "code": [".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".rb", ".php", ".swift", ".kt"],
    "config": [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".xml"],
    "document": [".md", ".txt", ".rst", ".doc", ".docx", ".pdf"],
    "data": [".csv", ".tsv", ".sql", ".parquet", ".jsonl"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"],
    "web": [".html", ".css", ".scss", ".less"],
    "devops": ["Dockerfile", "Makefile", ".sh", ".bash", "docker-compose.yml"],
}

class FileAgent(BaseAgent):

    agent_name = "file_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "file_management",
            "status": "ready",
            "capabilities": [
                "list_directory", "analyze_file",
                "find_files", "compare_files",
                "create_file", "write_file",
                "read_file", "delete_file",
                "generate_gitignore",
            ],
        }

    def handle_list_directory(
        self,
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 3,
        **kw: Any,
    ) -> dict[str, Any]:

        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"Path '{path}' does not exist")
        if not target.is_dir():
            raise ValueError(f"Path '{path}' is not a directory")

        entries: list[dict[str, Any]] = []
        total_size = 0
        type_counts: dict[str, int] = {}

        try:
            items = list(target.rglob("*") if recursive else target.iterdir())

            items = items[:500]

            for item in sorted(items):
                try:

                    if any(part.startswith(".") for part in item.relative_to(target).parts):
                        continue

                    entry: dict[str, Any] = {
                        "name": str(item.relative_to(target)),
                        "is_dir": item.is_dir(),
                    }

                    if item.is_file():
                        size = item.stat().st_size
                        entry["size_bytes"] = size
                        entry["size_human"] = self._human_size(size)
                        entry["extension"] = item.suffix.lower()
                        entry["category"] = self._categorize(item.suffix.lower(), item.name)
                        total_size += size

                        cat = entry["category"]
                        type_counts[cat] = type_counts.get(cat, 0) + 1

                    entries.append(entry)
                except (PermissionError, OSError):
                    continue

        except PermissionError:
            raise ValueError(f"Permission denied: '{path}'")

        return {
            "message": f"Listed {len(entries)} items in '{path}'",
            "path": str(target),
            "entries": entries[:100],
            "total_entries": len(entries),
            "total_size": self._human_size(total_size),
            "type_breakdown": type_counts,
            "truncated": len(entries) > 100,
        }

    def handle_analyze_file(
        self,
        path: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not path:
            raise ValueError("A file 'path' is required")

        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"File '{path}' does not exist")
        if not target.is_file():
            raise ValueError(f"'{path}' is not a file")

        stat = target.stat()
        ext = target.suffix.lower()

        analysis: dict[str, Any] = {
            "name": target.name,
            "path": str(target),
            "extension": ext,
            "category": self._categorize(ext, target.name),
            "size_bytes": stat.st_size,
            "size_human": self._human_size(stat.st_size),
            "created": time.ctime(stat.st_ctime),
            "modified": time.ctime(stat.st_mtime),
            "permissions": oct(stat.st_mode)[-3:],
        }

        if ext in (".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".csv", ".html", ".css"):
            try:
                content = target.read_text(errors="replace")
                lines = content.split("\n")
                analysis["line_count"] = len(lines)
                analysis["word_count"] = len(content.split())
                analysis["char_count"] = len(content)
                analysis["encoding"] = "utf-8"

                analysis["sha256"] = hashlib.sha256(content.encode()).hexdigest()[:16]

                analysis["preview"] = "\n".join(lines[:10])
                if len(lines) > 10:
                    analysis["preview"] += f"\n... ({len(lines) - 10} more lines)"

            except Exception as exc:
                analysis["read_error"] = str(exc)

        return {
            "message": f"Analyzed '{target.name}' ({analysis.get('size_human', 'unknown')})",
            **analysis,
        }

    def handle_find_files(
        self,
        path: str = ".",
        pattern: str = "*",
        extensions: list[str] | None = None,
        min_size: int = 0,
        max_size: int = 0,
        **kw: Any,
    ) -> dict[str, Any]:

        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"Path '{path}' does not exist")

        matches: list[dict[str, Any]] = []

        try:
            for item in target.rglob(pattern):
                if not item.is_file():
                    continue

                if extensions and item.suffix.lower() not in extensions:
                    continue

                try:
                    size = item.stat().st_size
                except OSError:
                    continue

                if min_size and size < min_size:
                    continue
                if max_size and size > max_size:
                    continue

                matches.append({
                    "path": str(item.relative_to(target)),
                    "size": self._human_size(size),
                    "modified": time.ctime(item.stat().st_mtime),
                })

                if len(matches) >= 200:
                    break

        except PermissionError:
            pass

        return {
            "message": f"Found {len(matches)} files matching '{pattern}'",
            "search_path": str(target),
            "pattern": pattern,
            "matches": matches[:100],
            "total_found": len(matches),
            "truncated": len(matches) > 100,
        }

    def handle_compare_files(
        self,
        file_a: str = "",
        file_b: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not file_a or not file_b:
            raise ValueError("Both 'file_a' and 'file_b' paths are required")

        path_a = Path(file_a).resolve()
        path_b = Path(file_b).resolve()

        if not path_a.exists() or not path_b.exists():
            raise ValueError("One or both files do not exist")

        try:
            lines_a = path_a.read_text(errors="replace").split("\n")
            lines_b = path_b.read_text(errors="replace").split("\n")
        except Exception as exc:
            raise ValueError(f"Could not read files: {exc}")

        additions = 0
        deletions = 0
        common = 0

        set_a = set(lines_a)
        set_b = set(lines_b)

        added = set_b - set_a
        removed = set_a - set_b
        unchanged = set_a & set_b

        return {
            "message": f"Compared '{path_a.name}' vs '{path_b.name}'",
            "file_a": {"name": path_a.name, "lines": len(lines_a)},
            "file_b": {"name": path_b.name, "lines": len(lines_b)},
            "lines_added": len(added),
            "lines_removed": len(removed),
            "lines_unchanged": len(unchanged),
            "similarity": round(len(unchanged) / max(len(set_a | set_b), 1), 2),
            "identical": lines_a == lines_b,
        }

    def handle_create_file(
        self,
        path: str = "",
        content: str = "",
        overwrite: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("A file 'path' is required")

        target = Path(path).resolve()

        if target.exists() and not overwrite:
            return {
                "message": f"File '{path}' already exists. Set overwrite=true to replace.",
                "created": False,
                "path": str(target),
            }

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        return {
            "message": f"File '{target.name}' created ({len(content)} chars)",
            "created": True,
            "path": str(target),
            "size": self._human_size(len(content.encode("utf-8"))),
            "lines": len(content.split("\n")),
        }

    def handle_write_file(
        self,
        path: str = "",
        content: str = "",
        append: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("A file 'path' is required")

        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if append and target.exists():
            existing = target.read_text(encoding="utf-8")
            content = existing + content

        target.write_text(content, encoding="utf-8")

        return {
            "message": f"{'Appended to' if append else 'Wrote'} '{target.name}' ({len(content)} chars)",
            "path": str(target),
            "size": self._human_size(len(content.encode("utf-8"))),
            "lines": len(content.split("\n")),
        }

    def handle_read_file(
        self,
        path: str = "",
        start_line: int = 0,
        end_line: int = 0,
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("A file 'path' is required")

        target = Path(path).resolve()
        if not target.exists():
            raise ValueError(f"File '{path}' does not exist")
        if not target.is_file():
            raise ValueError(f"'{path}' is not a file")

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        if start_line or end_line:
            start = max(0, start_line - 1)
            end = end_line if end_line else len(lines)
            lines = lines[start:end]
            content = "\n".join(lines)

        return {
            "message": f"Read '{target.name}' ({len(lines)} lines)",
            "path": str(target),
            "content": content,
            "total_lines": len(lines),
        }

    def handle_delete_file(
        self,
        path: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("A file 'path' is required")

        target = Path(path).resolve()
        if not target.exists():
            return {"message": f"File '{path}' does not exist", "deleted": False}

        if target.is_file():
            target.unlink()
            return {"message": f"Deleted '{target.name}'", "deleted": True, "path": str(target)}
        else:
            return {"message": f"'{path}' is a directory, not a file", "deleted": False}

    def handle_generate_gitignore(
        self,
        project_type: str = "python",
        extras: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        templates: dict[str, list[str]] = {
            "python": [
                "__pycache__/", "*.py[cod]", "*$py.class", "*.egg-info/",
                "dist/", "build/", ".eggs/", "*.egg",
                ".venv/", "venv/", "env/", ".env",
                ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
                "*.db", "*.sqlite3", ".coverage", "htmlcov/",
                "*.log", ".idea/", ".vscode/", "*.swp",
            ],
            "node": [
                "node_modules/", "dist/", "build/", ".next/",
                "*.log", "npm-debug.log*", ".env", ".env.local",
                ".cache/", ".parcel-cache/", "coverage/",
                ".idea/", ".vscode/", "*.swp",
            ],
            "go": [
                "bin/", "*.exe", "*.dll", "*.so", "*.dylib",
                "*.test", "*.out", "vendor/", ".env",
                ".idea/", ".vscode/",
            ],
            "rust": [
                "target/", "Cargo.lock", "*.pdb",
                ".env", ".idea/", ".vscode/",
            ],
            "general": [
                ".env", "*.log", ".DS_Store", "Thumbs.db",
                ".idea/", ".vscode/", "*.swp", "*.swo",
                ".cache/", "tmp/", "temp/",
            ],
        }

        entries = templates.get(project_type, templates["general"])
        if extras:
            entries.extend(extras)

        seen = set()
        unique = []
        for e in entries:
            if e not in seen:
                seen.add(e)
                unique.append(e)

        content = f"# .gitignore for {project_type} project\n"
        content += f"# Generated by StepWise AI\n\n"
        content += "\n".join(unique) + "\n"

        return {
            "message": f".gitignore generated for {project_type} ({len(unique)} entries)",
            "content": content,
            "project_type": project_type,
            "entries": len(unique),
        }

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @staticmethod
    def _categorize(ext: str, name: str) -> str:
        for category, extensions in _CATEGORIES.items():
            if ext in extensions or name in extensions:
                return category
        return "other"
