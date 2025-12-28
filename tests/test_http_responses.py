"""Tests for MCP HTTP response codes and headers."""

import pytest
import httpx


class TestResponseCodes:
    """Tests for HTTP response codes."""

    async def test_notification_returns_202(self, http_client: httpx.AsyncClient):
        """POST with notification (no id) returns 202 Accepted."""
        # First initialize to get a session
        init_response = await http_client.post(
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
        session_id = init_response.headers.get("Mcp-Session-Id")

        # Send a notification (no id field)
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "initialized"
                # No "id" field = notification
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        # Should return 202 Accepted with empty body
        assert response.status_code == 202
        assert response.text == "" or response.text is None or len(response.content) == 0

    async def test_request_returns_200_with_response(self, http_client: httpx.AsyncClient):
        """POST with request (has id) returns 200 OK with JSON body."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,  # Has id = request
                "method": "nudge_list_components",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "jsonrpc" in data
        assert "result" in data
        assert data["id"] == 1

    async def test_invalid_json_returns_400(self, http_client: httpx.AsyncClient):
        """Malformed JSON returns 400 Bad Request."""
        response = await http_client.post(
            "/",
            content=b"not valid json {{{",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400


class TestProtocolHeaders:
    """Tests for MCP protocol headers."""

    async def test_protocol_version_header(self, http_client: httpx.AsyncClient):
        """Responses include MCP-Protocol-Version header."""
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

        # Should have protocol version header
        version = response.headers.get("MCP-Protocol-Version")
        assert version is not None
        assert version == "2025-06-18"

    async def test_content_type_is_json(self, http_client: httpx.AsyncClient):
        """Response Content-Type is application/json for JSON responses."""
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
        content_type = response.headers.get("Content-Type")
        assert "application/json" in content_type
