import asyncio

import pytest

from mcp_local.auth import BearerAuthMiddleware

TOKEN = "s3cret-token"


def _make():
    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["type"])
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    return BearerAuthMiddleware(inner, TOKEN), calls


def _request(mw, path="/mcp", headers=None, query=b""):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": "http",
        "path": path,
        "headers": headers or [],
        "query_string": query,
    }
    asyncio.run(mw(scope, receive, send))
    return sent[0]["status"]


def test_no_credentials_is_401():
    mw, calls = _make()
    assert _request(mw) == 401
    assert calls == []


def test_wrong_bearer_is_401():
    mw, calls = _make()
    assert _request(mw, headers=[(b"authorization", b"Bearer nope")]) == 401
    assert calls == []


def test_wrong_scheme_is_401():
    mw, _ = _make()
    assert _request(mw, headers=[(b"authorization", f"Basic {TOKEN}".encode())]) == 401


def test_correct_bearer_passes():
    mw, calls = _make()
    assert _request(mw, headers=[(b"authorization", f"Bearer {TOKEN}".encode())]) == 200
    assert calls == ["http"]


def test_correct_query_token_passes():
    mw, _ = _make()
    assert _request(mw, query=f"token={TOKEN}".encode()) == 200


def test_wrong_query_token_is_401():
    mw, _ = _make()
    assert _request(mw, query=b"token=nope") == 401


def test_health_is_exempt():
    mw, _ = _make()
    assert _request(mw, path="/health") == 200


def test_lifespan_passes_through():
    mw, calls = _make()

    async def noop(*_):
        return None

    asyncio.run(mw({"type": "lifespan"}, noop, noop))
    assert calls == ["lifespan"]


def test_empty_token_rejected_at_construction():
    with pytest.raises(ValueError):
        BearerAuthMiddleware(lambda *a: None, "")
