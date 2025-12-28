"""Pytest fixtures for Nudge HTTP server tests."""

import asyncio
import pytest
import httpx
import threading
import time
from typing import AsyncGenerator, Generator

from nudge.http_server import NudgeHTTPServer
from nudge.server import NudgeServer


class TestServerContext:
    """Context for a running test server."""

    def __init__(self, port: int, server: NudgeServer, http_server: NudgeHTTPServer):
        self.port = port
        self.server = server
        self.http_server = http_server
        self._thread = None

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.port}"


@pytest.fixture
def server_context() -> Generator[TestServerContext, None, None]:
    """Start a PRIMARY server in a background thread and yield its context."""
    server = NudgeServer()
    http_server = NudgeHTTPServer(server._handle_rpc_request, port=0)  # port 0 = auto-assign

    # Start HTTP server and get actual port
    actual_port = http_server.start()

    # Run server in background thread
    def run_server():
        http_server.httpd.serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Give server time to start
    time.sleep(0.1)

    ctx = TestServerContext(actual_port, server, http_server)
    ctx._thread = thread

    yield ctx

    # Cleanup
    http_server.stop()


@pytest.fixture
async def http_client(server_context: TestServerContext) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client connected to test server."""
    async with httpx.AsyncClient(base_url=server_context.base_url) as client:
        yield client


@pytest.fixture
async def initialized_session(http_client: httpx.AsyncClient) -> str:
    """
    Complete MCP initialize handshake and return session ID.

    This fixture performs:
    1. POST initialize request
    2. Extract Mcp-Session-Id from response
    3. Return the session ID for use in subsequent requests
    """
    response = await http_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        },
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
    )

    assert response.status_code == 200, f"Initialize failed: {response.text}"
    session_id = response.headers.get("Mcp-Session-Id")
    assert session_id is not None, "No Mcp-Session-Id header in response"

    return session_id
