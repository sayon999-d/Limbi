#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="${LIMBI_INSTALL_REPO:-https://github.com/sayon999-d/Limbi-.git}"
INSTALL_SOURCE="${LIMBI_INSTALL_SOURCE:-pypi}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python 3.11+ is required to install Limbi."
    echo "Please install Python 3.11 and try again."
    exit 1
  fi
fi

PY_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"
if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
  echo "Python 3.11+ is required. Found: ${PY_VERSION}"
  echo "Install Python 3.11 and rerun this installer."
  exit 1
fi

echo "Limbi install check"
echo "Python: ${PY_VERSION}"
echo

if [[ "${INSTALL_SOURCE}" == "git" ]]; then
  echo "Installing Limbi from GitHub..."
  "$PYTHON_BIN" -m pip install --upgrade "git+${REPO_URL}@main#egg=limbi"
else
  echo "Installing Limbi from PyPI..."
  "$PYTHON_BIN" -m pip install --upgrade limbi
fi

echo
echo "Verifying installation..."
"$PYTHON_BIN" - <<'PY'
import limbi
print(getattr(limbi, "__version__", "installed"))
PY
echo
echo "Limbi is installed."
echo "Run: limbi"
