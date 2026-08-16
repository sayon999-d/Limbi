from __future__ import annotations

import re
from urllib.parse import urlparse


def extract_urls(text: str) -> list[str]:
    candidates = re.findall(r"https?://[^\s<>()\[\]{}]+", text)
    urls: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        cleaned = raw.rstrip(".,;:!?)]}'\"")
        parsed = urlparse(cleaned)
        if not parsed.scheme or not parsed.netloc:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        urls.append(cleaned)
    return urls


def looks_like_web_research_prompt(user_message: str) -> bool:
    text = user_message.lower()
    research_terms = (
        "latest",
        "recent",
        "news",
        "source",
        "sources",
        "article",
        "paper",
        "website",
        "link",
        "url",
        "research",
        "compare",
        "summarize",
        "summary",
        "search",
        "find",
        "look up",
        "fact check",
    )
    if any(term in text for term in research_terms):
        return True
    return bool(extract_urls(user_message))


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    pattern = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<code>.*?)\n```", re.DOTALL)
    for match in pattern.finditer(text or ""):
        blocks.append(
            {
                "language": str(match.group("lang") or "").strip().lower(),
                "content": str(match.group("code") or "").strip(),
            }
        )
    return blocks


def looks_like_file_creation_prompt(user_message: str) -> bool:
    text = user_message.lower()
    return (
        any(token in text for token in ("create", "build", "implement", "write", "generate"))
        and any(token in text for token in ("save", "workspace", "file", "project", "folder", "script", "app", "code"))
    )


def looks_like_actionable_code_task(user_message: str) -> bool:
    text = (user_message or "").lower()
    action_tokens = (
        "create",
        "build",
        "implement",
        "write",
        "generate",
        "save",
        "fix",
        "repair",
        "debug",
        "update",
        "edit",
        "change",
        "patch",
    )
    context_tokens = (
        "file",
        "workspace",
        "project",
        "folder",
        "script",
        "app",
        "code",
        "output",
        "error",
        "bug",
        "traceback",
        "exception",
        "source",
        "snippet",
    )
    return any(token in text for token in action_tokens) and any(token in text for token in context_tokens)


def is_tiny_prompt(user_message: str) -> bool:
    text = (user_message or "").strip()
    if not text:
        return False
    if len(text) <= 3 and not extract_urls(text):
        return True
    words = text.split()
    if len(words) == 1 and len(text) <= 4 and not any(ch.isdigit() for ch in text):
        return True
    return False


def needs_clarification(user_message: str) -> list[str]:
    text = user_message.lower().strip()
    words = text.split()

    task_verbs = {"build", "create", "make", "design", "write", "implement", "fix", "improve", "optimize", "generate"}
    vague_words = {"something", "stuff", "thing", "things", "whatever", "some", "it", "this", "that", "there", "here"}
    path_words = {"path", "file", "folder", "directory", "save", "write", "output"}
    explicit_targets = {
        "app", "project", "tool", "site", "api", "workflow", "agent",
        "calculator", "dashboard", "cli", "script", "page", "server",
        "component", "module", "service", "utility",
    }

    has_task = any(verb in text for verb in task_verbs)
    has_research_intent = looks_like_web_research_prompt(user_message)
    has_explicit_target = any(word in text for word in explicit_targets)
    has_vague_language = any(word in text for word in vague_words)
    has_path_context = any(word in text for word in path_words)

    if looks_like_actionable_code_task(user_message):
        return []

    if len(text) <= 3 and len(words) <= 1 and not extract_urls(user_message):
        return ["What exactly would you like me to do?"]

    if has_research_intent and len(words) <= 14:
        return []

    if not has_task:
        if has_vague_language and len(words) <= 8:
            return ["What exactly would you like me to do?"]
        return []

    if len(words) <= 8 and not has_explicit_target:
        return ["What exact output should I create or change?"]

    if has_path_context and not has_explicit_target and len(words) <= 16:
        return ["Where should I place the output in the workspace?"]

    return []


def extract_code_candidate(text: str) -> tuple[str, str]:
    code_blocks = extract_code_blocks(text)
    if code_blocks:
        best_block = max(code_blocks, key=lambda block: len(block.get("content", "")))
        content = str(best_block.get("content") or "").strip()
        language_hint = str(best_block.get("language") or "").strip()
        if content:
            return content, language_hint

    lowered = (text or "").lower()
    if any(token in lowered for token in ("def ", "class ", "import ", "from ", "function ", "const ", "let ", "var ", "return ", "<html", "#!/bin/bash")):
        return text.strip(), ""

    return "", ""
