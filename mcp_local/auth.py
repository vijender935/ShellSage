"""Bearer-token authentication for the remote MCP endpoint (pure ASGI middleware).

A request is accepted if it carries the shared secret in EITHER:
  - header:        Authorization: Bearer <token>
  - query string:  ?token=<token>   (for MCP clients that only accept a URL)

Comparison is constant-time. The lifespan scope is always passed through so the
wrapped app can start/stop normally.
"""
from __future__ import annotations

import hmac
from urllib.parse import parse_qs

_UNAUTHORIZED_BODY = b'{"error":"unauthorized"}'


class BearerAuthMiddleware:
    def __init__(self, app, token: str, exempt_paths: tuple[str, ...] = ("/health",)):
        token = (token or "").strip()
        if not token:
            raise ValueError("BearerAuthMiddleware requires a non-empty token")
        self.app = app
        self._token = token.encode()
        self._exempt = frozenset(exempt_paths)

    def _presented_token(self, scope) -> bytes:
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                scheme, _, cred = value.partition(b" ")
                if scheme.lower() == b"bearer":
                    return cred.strip()
                break
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        values = query.get("token")
        return values[0].encode() if values else b""

    def _authorized(self, scope) -> bool:
        return hmac.compare_digest(self._presented_token(scope), self._token)

    async def __call__(self, scope, receive, send):
        kind = scope["type"]

        if kind == "lifespan":
            await self.app(scope, receive, send)
            return

        if kind == "http":
            if scope.get("path") in self._exempt or self._authorized(scope):
                await self.app(scope, receive, send)
                return
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            })
            await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})
            return

        # websocket or anything else: not used by this server, deny.
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008})
