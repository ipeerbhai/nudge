"""Tests for MCP protocol compliance."""

import pytest
import httpx


class TestFullHandshake:
    """Tests for complete MCP handshake flow."""

    async def test_full_mcp_handshake(self, http_client: httpx.AsyncClient):
        """Complete initialize -> initialized -> tools/list flow."""
        # Step 1: Initialize
        init_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        assert init_response.status_code == 200
        session_id = init_response.headers.get("Mcp-Session-Id")
        assert session_id is not None

        init_data = init_response.json()
        assert "result" in init_data
        result = init_data["result"]
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result

        # Step 2: Initialized notification
        initialized_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "initialized"
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        assert initialized_response.status_code == 202

        # Step 3: List tools
        tools_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        assert tools_response.status_code == 200
        tools_data = tools_response.json()
        assert "result" in tools_data
        assert "tools" in tools_data["result"]
        assert len(tools_data["result"]["tools"]) > 0


class TestCapabilities:
    """Tests for capability reporting."""

    async def test_capability_reporting(self, http_client: httpx.AsyncClient):
        """Server reports correct capabilities."""
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
        result = data["result"]

        # Must have capabilities object
        assert "capabilities" in result
        capabilities = result["capabilities"]

        # Should indicate tool support
        assert "tools" in capabilities

    async def test_server_info_present(self, http_client: httpx.AsyncClient):
        """Server info is present in initialize response."""
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
        result = data["result"]

        # Must have serverInfo
        assert "serverInfo" in result
        server_info = result["serverInfo"]
        assert "name" in server_info
        assert "version" in server_info


class TestErrorFormat:
    """Tests for error response format."""

    async def test_error_response_format(self, http_client: httpx.AsyncClient):
        """Errors follow JSON-RPC 2.0 format."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nonexistent_method",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200  # JSON-RPC errors still return 200

        data = response.json()

        # Should have error, not result
        assert "error" in data
        assert "result" not in data

        error = data["error"]
        assert "code" in error
        assert "message" in error

        # ID should be preserved
        assert data["id"] == 1

    async def test_jsonrpc_version_in_response(self, http_client: httpx.AsyncClient):
        """Responses include jsonrpc version."""
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

        data = response.json()
        assert data.get("jsonrpc") == "2.0"
