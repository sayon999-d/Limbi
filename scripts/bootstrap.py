from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_TOOLS = ["git", "rg", "ffmpeg"]
OPTIONAL_TOOLS = ["node", "npm"]


def _version_ok() -> bool:
    return sys.version_info >= (3, 11)


def _tool_exists(tool: str) -> bool:
    return shutil.which(tool) is not None


def _tool_version(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        return "missing"
    try:
        result = subprocess.run([tool, "--version"], capture_output=True, text=True, check=False)
        output = (result.stdout or result.stderr or "").strip()
        return output.splitlines()[0] if output else "available"
    except Exception:
        return "available"


def main() -> int:
    print("Limbi bootstrap check")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]} {'OK' if _version_ok() else 'needs 3.11+'}")
    print()

    missing: list[str] = []
    for tool in REQUIRED_TOOLS:
        ok = _tool_exists(tool)
        print(f"{tool}: {'OK' if ok else 'missing'}")
        if ok:
            print(f"  { _tool_version(tool) }")
        else:
            missing.append(tool)

    print()
    for tool in OPTIONAL_TOOLS:
        ok = _tool_exists(tool)
        print(f"{tool}: {'OK' if ok else 'missing'}")
        if ok:
            print(f"  { _tool_version(tool) }")

    print()
    if not _version_ok():
        missing.append("python 3.11+")

    if missing:
        print("Missing prerequisites:")
        for item in missing:
            print(f" - {item}")
        print()
        print("Suggested next steps:")
        if sys.platform == "darwin":
            print(" - macOS: brew install python@3.11 node ripgrep ffmpeg git")
        elif sys.platform.startswith("linux"):
            print(" - Debian/Ubuntu: sudo apt install python3.11 nodejs ripgrep ffmpeg git")
            print(" - Fedora: sudo dnf install python3.11 nodejs ripgrep ffmpeg git")
        elif sys.platform.startswith("win"):
            print(" - Windows: install Python 3.11, Node.js, Git, ripgrep, and ffmpeg via winget or Chocolatey")
        else:
            print(" - Install the missing tools using your platform package manager")
        return 1

    print("All required tools are available.")
    print("You can now run: python -m pip install -e .")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
