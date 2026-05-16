from __future__ import annotations

"""
Compatibility alias for the canonical `limbi.agents` package.

The root `agents` import path remains available for older code, but all runtime
loads now resolve to `limbi.agents` so the packaged tree is the source of truth.
"""

import importlib
import sys


_canonical = importlib.import_module("limbi.agents")
sys.modules[__name__] = _canonical

globals().update(_canonical.__dict__)
