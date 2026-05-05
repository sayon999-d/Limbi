from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("limbi.ratelimit")

class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, dict[str, Any]]:
        now = time.time()
        window_start = now - self.window

        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        remaining = self.max_requests - len(self._requests[key])
        info = {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(max(remaining, 0)),
            "X-RateLimit-Window": str(self.window),
        }

        if remaining <= 0:
            oldest = min(self._requests[key]) if self._requests[key] else now
            retry_after = int(oldest + self.window - now) + 1
            info["Retry-After"] = str(retry_after)
            return False, info

        self._requests[key].append(now)
        return True, info

class ConcurrencyLimiter:
    def __init__(self, max_concurrent: int = 3) -> None:
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._current = 0

    async def acquire(self) -> bool:
        if self._current >= self.max_concurrent:
            return False
        await self._semaphore.acquire()
        self._current += 1
        return True

    def release(self) -> None:
        self._current = max(0, self._current - 1)
        self._semaphore.release()

    @property
    def available(self) -> int:
        return self.max_concurrent - self._current

_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
_llm_concurrency = ConcurrencyLimiter(max_concurrent=3)

_PUBLIC_EXACT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
_PUBLIC_PREFIXES = ("/ui", "/extension")

def get_cors_origins() -> list[str]:
    raw = os.getenv("LIMBI_CORS_ORIGINS", "").strip()
    if raw:
        origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins

    return [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:7860",
        "http://localhost:7860",
    ]

def get_api_key() -> str:
    return os.getenv("LIMBI_API_KEY", "").strip()

def _extract_auth_token(request: Request) -> str:
    header_key = request.headers.get("X-Limbi-API-Key", "").strip()
    if header_key:
        return header_key

    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return auth_header

def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)

class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        expected_key = get_api_key()
        if not expected_key or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/") or _is_public_path(path):
            return await call_next(request)

        provided_key = _extract_auth_token(request)
        if not provided_key or not hmac.compare_digest(provided_key, expected_key):
            logger.warning("Unauthorized request blocked on %s", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)

class RateLimitMiddleware(BaseHTTPMiddleware):
    RATE_LIMITED_PATHS = {"/api/chat"}
    CONCURRENCY_LIMITED_PATHS = {"/api/chat"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        if any(path.startswith(p) for p in self.RATE_LIMITED_PATHS):
            allowed, info = _rate_limiter.is_allowed(client_ip)
            if not allowed:
                logger.warning("Rate limited: %s on %s", client_ip, path)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please slow down.",
                        "retry_after": int(info.get("Retry-After", 10)),
                    },
                    headers=info,
                )

        needs_concurrency = any(
            path.startswith(p) for p in self.CONCURRENCY_LIMITED_PATHS
        )
        if needs_concurrency:
            acquired = await _llm_concurrency.acquire()
            if not acquired:
                logger.warning("LLM concurrency limit hit: %s", path)
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Server busy - LLM is processing other requests. Retry shortly.",
                        "concurrent_limit": _llm_concurrency.max_concurrent,
                    },
                    headers={"Retry-After": "5"},
                )

        try:
            response = await call_next(request)

            if any(path.startswith(p) for p in self.RATE_LIMITED_PATHS):
                _, info = _rate_limiter.is_allowed(f"{client_ip}_peek")
                for k, v in info.items():
                    if k.startswith("X-"):
                        response.headers[k] = v

            return response
        finally:
            if needs_concurrency:
                _llm_concurrency.release()

def get_rate_limit_status() -> dict[str, Any]:
    return {
        "rate_limit": {
            "max_per_minute": _rate_limiter.max_requests,
            "window_seconds": _rate_limiter.window,
        },
        "concurrency": {
            "max_concurrent_llm": _llm_concurrency.max_concurrent,
            "available_slots": _llm_concurrency.available,
        },
        "auth": {
            "enabled": bool(get_api_key()),
            "protected_paths": ["/api/*"],
        },
    }
