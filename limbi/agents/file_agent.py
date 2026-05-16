

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from . import BaseAgent
from limbi.permissions import require_permission
from limbi.workspace import load_config

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

_LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
    "tsx": ".tsx",
    "jsx": ".jsx",
    "go": ".go",
    "golang": ".go",
    "rust": ".rs",
    "rs": ".rs",
    "java": ".java",
    "c": ".c",
    "cpp": ".cpp",
    "c++": ".cpp",
    "rb": ".rb",
    "ruby": ".rb",
    "php": ".php",
    "swift": ".swift",
    "kt": ".kt",
    "kotlin": ".kt",
    "bash": ".sh",
    "shell": ".sh",
    "sh": ".sh",
    "html": ".html",
    "css": ".css",
    "json": ".json",
    "yaml": ".yaml",
    "yml": ".yml",
}

class FileAgent(BaseAgent):

    agent_name = "file_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "file_management",
            "status": "ready",
            "capabilities": [
                "create_file", "write_file", "read_file",
                "modify_file", "delete_file",
                "rename_file", "copy_file", "move_file",
                "create_directory", "delete_directory",
                "list_directory", "find_files",
                "analyze_file", "compare_files",
                "set_permissions", "execute_file",
                "generate_gitignore",
            ],
        }

    def _resolve_path(self, path: str = "", **kw: Any) -> str:
        candidates = (
            path,
            kw.get("path"),
            kw.get("file_path"),
            kw.get("filepath"),
            kw.get("file_name"),
            kw.get("filename"),
            kw.get("name"),
            kw.get("target_path"),
            kw.get("output_path"),
            kw.get("destination"),
        )
        workspace_root = Path(
            os.getenv("LIMBI_WORKSPACE_ROOT")
            or os.getenv("WORKSPACE_ROOT")
            or Path.cwd()
        ).expanduser().resolve()
        allow_outside = os.getenv("LIMBI_ALLOW_OUTSIDE_WORKSPACE", "").strip().lower() in ("1", "true", "yes", "on")
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                raw = Path(candidate.strip()).expanduser()
                raw_text = str(raw)
                if raw_text == "/workspace" or raw_text.startswith("/workspace/"):
                    suffix = raw_text.removeprefix("/workspace").lstrip("/")
                    return str((workspace_root / suffix).resolve())
                if raw_text == "/workspaces" or raw_text.startswith("/workspaces/"):
                    suffix = raw_text.removeprefix("/workspaces").lstrip("/")
                    return str((workspace_root / suffix).resolve())
                if raw.is_absolute():
                    resolved = raw.resolve()
                    if allow_outside:
                        return str(resolved)
                    if workspace_root in resolved.parents or resolved == workspace_root:
                        return str(resolved)
                    raise PermissionError(f"Path '{resolved}' is outside the workspace root '{workspace_root}'")
                return str((workspace_root / raw).resolve())
        raise ValueError("A file 'path' is required")

    def _safe_workspace_target(self, path: str = "", **kw: Any) -> Path:
        return Path(self._resolve_path(path, **kw))

    def _require_filesystem_access(self, action: str) -> None:
        config = load_config()
        require_permission(config, "filesystem", self.agent_name, action)

    def _infer_language(self, language: str = "", content: str = "", path: str = "") -> str:
        explicit = (language or "").strip().lower()
        if explicit:
            return explicit
        suffix = Path(path).suffix.lower()
        if suffix:
            for key, ext in _LANGUAGE_EXTENSIONS.items():
                if ext == suffix:
                    return key
        snippet = content.lstrip()
        if snippet.startswith("#!/usr/bin/env python") or "import " in content or "def " in content or "class " in content:
            return "python"
        if "console.log" in content or "function " in content or "const " in content or "let " in content or "var " in content:
            return "javascript"
        if "interface " in content or "type " in content:
            return "typescript"
        if "package main" in content or "func main" in content:
            return "go"
        if "#!/bin/bash" in content or "set -e" in content:
            return "bash"
        return ""

    def _normalize_target_path(self, path: str, language: str = "", content: str = "") -> tuple[str, str]:
        resolved = Path(self._resolve_path(path)).expanduser().resolve()
        inferred_language = self._infer_language(language, content, str(resolved))
        if not resolved.suffix and inferred_language:
            suffix = _LANGUAGE_EXTENSIONS.get(inferred_language.lower(), "")
            if suffix:
                resolved = resolved.with_suffix(suffix)
        return str(resolved), inferred_language

    def handle_list_directory(
        self,
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 3,
        **kw: Any,
    ) -> dict[str, Any]:

        target = self._safe_workspace_target(path, **kw)
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

        target = self._safe_workspace_target(path, **kw)
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

        target = self._safe_workspace_target(path, **kw)
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

        path_a = self._safe_workspace_target(file_a, **kw)
        path_b = self._safe_workspace_target(file_b, **kw)

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
        language: str = "",
        overwrite: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("create_file")
        path = self._resolve_path(path, **kw)
        target_path, inferred_language = self._normalize_target_path(path, language=language, content=content)
        target = self._safe_workspace_target(target_path)

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
            "language": inferred_language or Path(target).suffix.lstrip("."),
            "size": self._human_size(len(content.encode("utf-8"))),
            "lines": len(content.split("\n")),
        }

    def handle_write_file(
        self,
        path: str = "",
        content: str = "",
        language: str = "",
        append: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("write_file")
        path = self._resolve_path(path, **kw)
        target_path, inferred_language = self._normalize_target_path(path, language=language, content=content)
        target = self._safe_workspace_target(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if append and target.exists():
            existing = target.read_text(encoding="utf-8")
            content = existing + content

        target.write_text(content, encoding="utf-8")

        return {
            "message": f"{'Appended to' if append else 'Wrote'} '{target.name}' ({len(content)} chars)",
            "path": str(target),
            "language": inferred_language or target.suffix.lstrip("."),
            "size": self._human_size(len(content.encode("utf-8"))),
            "lines": len(content.split("\n")),
        }

    def handle_write_to_file(
        self,
        path: str = "",
        content: str = "",
        language: str = "",
        append: bool = False,
        overwrite: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("write_to_file")
        return self.handle_write_file(path=path, content=content, language=language, append=append, **kw)

    def handle_save(
        self,
        path: str = "",
        content: str = "",
        language: str = "",
        append: bool = False,
        overwrite: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("save")
        return self.handle_write_to_file(
            path=path,
            content=content,
            language=language,
            append=append,
            overwrite=overwrite,
            **kw,
        )

    def handle_read_file(
        self,
        path: str = "",
        start_line: int = 0,
        end_line: int = 0,
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("modify_file")
        if not path:
            raise ValueError("A file 'path' is required")

        target = self._safe_workspace_target(path, **kw)
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

        target = self._safe_workspace_target(path, **kw)
        if not target.exists():
            return {"message": f"File '{path}' does not exist", "deleted": False}

        if target.is_file():
            target.unlink()
            return {"message": f"Deleted '{target.name}'", "deleted": True, "path": str(target)}
        else:
            return {"message": f"'{path}' is a directory, not a file", "deleted": False}

    def handle_modify_file(
        self,
        path: str = "",
        find: str = "",
        replace: str = "",
        insert_at_line: int = 0,
        insert_content: str = "",
        delete_lines: list[int] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("A file 'path' is required")

        target = self._safe_workspace_target(path, **kw)
        if not target.exists():
            raise ValueError(f"File '{path}' does not exist")
        if not target.is_file():
            raise ValueError(f"'{path}' is not a file")

        content = target.read_text(encoding="utf-8")
        lines = content.split("\n")
        changes: list[str] = []

        if find and replace is not None:
            count = content.count(find)
            if count == 0:
                return {
                    "message": f"Pattern not found in '{target.name}'",
                    "modified": False,
                    "path": str(target),
                }
            content = content.replace(find, replace)
            lines = content.split("\n")
            changes.append(f"Replaced {count} occurrence(s)")

        if insert_at_line and insert_content:
            idx = max(0, min(insert_at_line - 1, len(lines)))
            new_lines = insert_content.split("\n")
            lines = lines[:idx] + new_lines + lines[idx:]
            content = "\n".join(lines)
            changes.append(f"Inserted {len(new_lines)} line(s) at line {insert_at_line}")

        if delete_lines:
            to_delete = set(delete_lines)
            lines = [l for i, l in enumerate(lines, 1) if i not in to_delete]
            content = "\n".join(lines)
            changes.append(f"Deleted {len(to_delete)} line(s)")

        target.write_text(content, encoding="utf-8")

        return {
            "message": f"Modified '{target.name}': {'; '.join(changes)}",
            "modified": True,
            "path": str(target),
            "changes": changes,
            "total_lines": len(lines),
        }

    def handle_rename_file(
        self,
        path: str = "",
        new_name: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("rename_file")
        if not path or not new_name:
            raise ValueError("Both 'path' and 'new_name' are required")

        source = self._safe_workspace_target(path, **kw)
        if not source.exists():
            raise ValueError(f"'{path}' does not exist")

        destination = source.parent / new_name
        if destination.exists():
            return {
                "message": f"'{new_name}' already exists in the same directory",
                "renamed": False,
            }

        source.rename(destination)

        return {
            "message": f"Renamed '{source.name}' to '{new_name}'",
            "renamed": True,
            "old_path": str(source),
            "new_path": str(destination),
        }

    def handle_copy_file(
        self,
        source: str = "",
        destination: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        import shutil

        self._require_filesystem_access("copy_file")
        if not source or not destination:
            raise ValueError("Both 'source' and 'destination' are required")

        src = self._safe_workspace_target(source, **kw)
        if not src.exists():
            raise ValueError(f"Source '{source}' does not exist")

        dst = self._safe_workspace_target(destination, **kw)
        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))

        return {
            "message": f"Copied '{src.name}' to '{dst}'",
            "copied": True,
            "source": str(src),
            "destination": str(dst),
        }

    def handle_move_file(
        self,
        source: str = "",
        destination: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        import shutil

        self._require_filesystem_access("move_file")
        if not source or not destination:
            raise ValueError("Both 'source' and 'destination' are required")

        src = self._safe_workspace_target(source, **kw)
        if not src.exists():
            raise ValueError(f"Source '{source}' does not exist")

        dst = self._safe_workspace_target(destination, **kw)
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(src), str(dst))

        return {
            "message": f"Moved '{src.name}' to '{dst}'",
            "moved": True,
            "source": str(src),
            "destination": str(dst),
        }

    def handle_create_directory(
        self,
        path: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("create_directory")
        if not path:
            raise ValueError("A directory 'path' is required")

        target = self._safe_workspace_target(path, **kw)
        if target.exists():
            return {
                "message": f"Directory '{path}' already exists",
                "created": False,
                "path": str(target),
            }

        target.mkdir(parents=True, exist_ok=True)

        return {
            "message": f"Directory '{target.name}' created",
            "created": True,
            "path": str(target),
        }

    def handle_delete_directory(
        self,
        path: str = "",
        force: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        import shutil

        self._require_filesystem_access("delete_directory")
        if not path:
            raise ValueError("A directory 'path' is required")

        target = self._safe_workspace_target(path, **kw)
        if not target.exists():
            return {"message": f"Directory '{path}' does not exist", "deleted": False}
        if not target.is_dir():
            return {"message": f"'{path}' is not a directory", "deleted": False}

        children = list(target.iterdir())
        if children and not force:
            return {
                "message": f"Directory '{target.name}' is not empty ({len(children)} items). Set force=true to delete.",
                "deleted": False,
                "item_count": len(children),
            }

        shutil.rmtree(str(target))

        return {
            "message": f"Deleted directory '{target.name}'",
            "deleted": True,
            "path": str(target),
        }

    def handle_set_permissions(
        self,
        path: str = "",
        mode: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        self._require_filesystem_access("set_permissions")
        if not path or not mode:
            raise ValueError("Both 'path' and 'mode' (e.g. '755') are required")

        target = self._safe_workspace_target(path, **kw)
        if not target.exists():
            raise ValueError(f"'{path}' does not exist")

        try:
            octal_mode = int(mode, 8)
        except ValueError:
            raise ValueError(f"Invalid mode '{mode}'. Use octal format like '755' or '644'")

        os.chmod(str(target), octal_mode)

        return {
            "message": f"Permissions set to {mode} on '{target.name}'",
            "path": str(target),
            "mode": mode,
        }

    def handle_execute_file(
        self,
        path: str = "",
        args: list[str] | None = None,
        timeout: int = 30,
        **kw: Any,
    ) -> dict[str, Any]:
        import subprocess

        self._require_filesystem_access("execute_file")
        if not path:
            raise ValueError("A file 'path' is required")

        target = self._safe_workspace_target(path, **kw)
        if not target.exists():
            raise ValueError(f"File '{path}' does not exist")

        ext = target.suffix.lower()
        cmd: list[str] = []

        if ext == ".py":
            cmd = ["python3", str(target)]
        elif ext == ".sh" or ext == ".bash":
            cmd = ["bash", str(target)]
        elif ext == ".js":
            cmd = ["node", str(target)]
        elif ext == ".ts":
            cmd = ["npx", "ts-node", str(target)]
        else:
            if os.access(str(target), os.X_OK):
                cmd = [str(target)]
            else:
                return {
                    "message": f"Cannot determine how to execute '{target.name}' (ext: {ext})",
                    "executed": False,
                }

        if args:
            cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(target.parent),
            )

            return {
                "message": f"Executed '{target.name}' (exit code: {result.returncode})",
                "executed": True,
                "exit_code": result.returncode,
                "stdout": result.stdout[:5000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            return {
                "message": f"Execution timed out after {timeout}s",
                "executed": False,
                "timeout": True,
            }
        except FileNotFoundError as exc:
            return {
                "message": f"Runtime not found: {exc}",
                "executed": False,
            }

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
