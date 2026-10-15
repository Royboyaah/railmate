"""HTTP middleware: request logging, security headers and rate limiting."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("railmate.http")

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds a request id, security headers and one structured log line per request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not request.url.path.startswith(DOCS_PATHS):   # Swagger UI loads its own CDN assets
            response.headers["Content-Security-Policy"] = CSP
        if request.url.path.startswith("/api"):
            log.info("%s %s %s %.1fms id=%s", request.method, request.url.path,
                     response.status_code, elapsed, request_id)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window limiter per client IP, applied to /api routes.
    Auth endpoints get a stricter limit to slow down password guessing.
    Note: state is in-process memory - use Redis or a gateway limiter when
    running multiple instances.
    """

    def __init__(self, app, per_minute: int = 120, auth_per_minute: int = 10):
        super().__init__(app)
        self.per_minute = per_minute
        self.auth_per_minute = auth_per_minute
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or self.per_minute <= 0:
            return await call_next(request)
        is_auth = path.startswith("/api/auth/") and request.method == "POST"
        limit = self.auth_per_minute if is_auth else self.per_minute
        client = request.client.host if request.client else "unknown"
        bucket = self.hits[(client, "auth" if is_auth else "api")]
        now = time.monotonic()
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = int(60 - (now - bucket[0])) + 1
            return JSONResponse({"detail": "Too many requests - please slow down"},
                                status_code=429, headers={"Retry-After": str(retry)})
        bucket.append(now)
        return await call_next(request)
