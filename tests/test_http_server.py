"""Tests for MCP HTTP server functionality."""

import pytest
import httpx


class TestLegacyCompatibility:
    """Tests ensuring backward compatibility with existing clients."""

    async def test_legacy_jsonrpc_post_still_works(self, http_client: httpx.AsyncClient):
        """Existing clients without session headers should still work."""
        # POST a tool call without any MCP session headers
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "jsonrpc" in data
        assert data.get("id") == 1
        # Should have result, not error
        assert "result" in data or "error" not in data

    async def test_health_endpoint_unchanged(self, http_client: httpx.AsyncClient):
        """GET /health returns status without session requirements."""
        response = await http_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "pid" in data


class TestMCPInitialize:
    """Tests for MCP initialize handshake."""

    async def test_initialize_returns_session_id(self, http_client: httpx.AsyncClient):
        """POST initialize request returns Mcp-Session-Id header."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        assert response.status_code == 200

        # Must have Mcp-Session-Id header
        session_id = response.headers.get("Mcp-Session-Id")
        assert session_id is not None, "Response missing Mcp-Session-Id header"
        assert len(session_id) > 0

        # Response body should be valid JSON-RPC
        data = response.json()
        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == 1
        assert "result" in data

    async def test_session_id_format(self, http_client: httpx.AsyncClient):
        """Session ID contains only visible ASCII (0x21-0x7E)."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        session_id = response.headers.get("Mcp-Session-Id")
        assert session_id is not None

        # Check all characters are visible ASCII (0x21-0x7E)
        for char in session_id:
            code = ord(char)
            assert 0x21 <= code <= 0x7E, f"Invalid character in session ID: {char!r} (code {code})"

    async def test_initialize_returns_capabilities(self, http_client: httpx.AsyncClient):
        """Initialize response includes server capabilities."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        data = response.json()
        result = data.get("result", {})

        # Should have protocolVersion
        assert "protocolVersion" in result

        # Should have capabilities object
        assert "capabilities" in result

        # Should have serverInfo
        assert "serverInfo" in result


class TestOriginValidation:
    """Tests for Origin header security validation."""

    async def test_origin_header_localhost_allowed(self, http_client: httpx.AsyncClient):
        """Requests from localhost origins are allowed."""
        for origin in ["http://localhost", "http://localhost:8080", "http://127.0.0.1"]:
            response = await http_client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "nudge_list_components",
                    "params": {}
                },
                headers={
                    "Content-Type": "application/json",
                    "Origin": origin,
                }
            )
            # Should not be rejected
            assert response.status_code != 403, f"Origin {origin} was rejected"

    async def test_origin_header_external_rejected(self, http_client: httpx.AsyncClient):
        """Requests from external origins are rejected (DNS rebinding protection)."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Origin": "http://evil.com",
            }
        )

        # Should be rejected with 403 Forbidden
        assert response.status_code == 403


class TestSessionEcho:
    """Tests for session ID handling in responses."""

    async def test_session_id_echoed_in_responses(
        self, http_client: httpx.AsyncClient, initialized_session: str
    ):
        """Responses include the same Mcp-Session-Id that was sent."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": initialized_session,
            }
        )

        assert response.status_code == 200

        # Response should echo back the session ID
        response_session = response.headers.get("Mcp-Session-Id")
        assert response_session == initialized_session
