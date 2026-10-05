"""Bearer authentication plus bounded HTTP request controls."""
from __future__ import annotations
import hashlib
import hmac
import time
from collections import defaultdict, deque
from contextvars import ContextVar
_UNAUTHORIZED_BODY=b'{"error":"unauthorized"}'
_TOO_LARGE_BODY=b'{"error":"request_too_large"}'
_RATE_BODY=b'{"error":"rate_limited"}'
_auth_identity: ContextVar[str|None] = ContextVar("auth_identity", default=None)

def current_identity() -> str|None:
    return _auth_identity.get()

def _identity(token: bytes) -> str:
    return hashlib.sha256(token).hexdigest()

class BearerAuthMiddleware:
    def __init__(self, app, token: str, exempt_paths: tuple[str,...]=("/health",),
                 max_body_bytes: int=1_048_576, requests_per_minute: int=60):
        token=(token or "").strip()
        if not token: raise ValueError("BearerAuthMiddleware requires a non-empty token")
        if max_body_bytes < 1024: raise ValueError("max_body_bytes is too small")
        if requests_per_minute < 1: raise ValueError("requests_per_minute must be positive")
        self.app=app
        self._token=token.encode()
        self._identity=_identity(self._token)
        self._exempt=frozenset(exempt_paths)
        self._max_body=max_body_bytes
        self._rpm=requests_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _presented_token(self, scope)->bytes:
        for key,value in scope.get("headers",[]):
            if key==b"authorization":
                scheme,_,cred=value.partition(b" ")
                if scheme.lower()==b"bearer": return cred.strip()
                break
        return b""

    def _authorized(self,scope)->bool:
        return hmac.compare_digest(self._presented_token(scope),self._token)

    def _rate_allowed(self,key:str)->bool:
        now=time.monotonic()
        q=self._hits[key]
        while q and now-q[0]>=60: q.popleft()
        if len(q)>=self._rpm: return False
        q.append(now)
        return True

    def _limited_receive(self,receive):
        seen=0
        async def wrapped():
            nonlocal seen
            message=await receive()
            if message.get("type")=="http.request":
                body=message.get("body",b"") or b""
                seen += len(body)
                if seen > self._max_body:
                    raise _RequestTooLarge
            return message
        return wrapped

    async def __call__(self,scope,receive,send):
        kind=scope["type"]
        if kind=="lifespan":
            await self.app(scope,receive,send); return
        if kind=="http":
            path=scope.get("path")
            if path in self._exempt:
                await self.app(scope,receive,send); return
            if not self._authorized(scope):
                await send({"type":"http.response.start","status":401,"headers":[(b"content-type",b"application/json"),(b"www-authenticate",b"Bearer")]})
                await send({"type":"http.response.body","body":_UNAUTHORIZED_BODY}); return
            if not self._rate_allowed(self._identity):
                await send({"type":"http.response.start","status":429,"headers":[(b"content-type",b"application/json"),(b"retry-after",b"60")]})
                await send({"type":"http.response.body","body":_RATE_BODY}); return
            token=_auth_identity.set(self._identity)
            try:
                await self.app(scope,self._limited_receive(receive),send)
            except _RequestTooLarge:
                await send({"type":"http.response.start","status":413,"headers":[(b"content-type",b"application/json")]})
                await send({"type":"http.response.body","body":_TOO_LARGE_BODY})
            finally:
                _auth_identity.reset(token)
            return
        if kind=="websocket":
            await send({"type":"websocket.close","code":1008})

class _RequestTooLarge(Exception):
    pass
