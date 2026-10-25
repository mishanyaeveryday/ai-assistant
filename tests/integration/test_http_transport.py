"""Servers reached over streamable HTTP, through the real SDK transport.

A local server stands in for a remote one and turns away any request without
the right Authorization header, so these show that headers configured in
settings reach the server - for the connection check and for tool calls.
"""
import asyncio
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from agent.mcp_client import ConnectionSpec, MCPClient  # noqa: E402
from agent.mcp_probe import probe  # noqa: E402

TOKEN_HEADERS = {"Authorization": "Bearer test-token"}


def _require_token(app):
    async def guarded(scope, receive, send):
        if (scope["type"] == "http"
                and dict(scope["headers"]).get(b"authorization") != b"Bearer test-token"):
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
        await app(scope, receive, send)
    return guarded


@pytest.fixture(scope="module")
def server_url():
    mcp = FastMCP("echo")

    @mcp.tool()
    def echo(text: str) -> str:
        return text

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        _require_token(mcp.streamable_http_app()),
        host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The test server did not start")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=5)


def test_check_passes_with_the_configured_headers(server_url):
    result = asyncio.run(probe("http", url=server_url, headers=TOKEN_HEADERS))

    assert result.ok, result.message
    assert result.tools == ("echo",)


def test_check_without_the_token_reports_the_refusal(server_url):
    result = asyncio.run(probe("http", url=server_url))

    assert not result.ok
    assert result.code == "http_401"


def test_tool_call_carries_the_configured_headers(server_url):
    spec = ConnectionSpec(id="remote", name="remote", transport="http",
                          url=server_url, headers=TOKEN_HEADERS)

    async def scenario():
        async with MCPClient() as client:
            try:
                return await client.call_tool(spec, "echo", {"text": "hi"})
            finally:
                await client.close_all()

    result = asyncio.run(scenario())

    assert not result.isError
    assert result.content[0].text == "hi"
