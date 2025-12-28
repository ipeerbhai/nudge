"""Tests for MCP protocol methods via HTTP."""

import pytest
import httpx


class TestToolsList:
    """Tests for tools/list method."""

    async def test_tools_list_via_http(self, http_client: httpx.AsyncClient):
        """tools/list method returns list of tools."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        result = data["result"]
        assert "tools" in result

        tools = result["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check that nudge tools are present
        tool_names = [t["name"] for t in tools]
        assert "nudge_set_hint" in tool_names
        assert "nudge_get_hint" in tool_names
        assert "nudge_query" in tool_names

    async def test_tools_list_returns_input_schemas(self, http_client: httpx.AsyncClient):
        """tools/list returns inputSchema for each tool."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        data = response.json()
        tools = data["result"]["tools"]

        for tool in tools:
            assert "name" in tool
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)


class TestToolsCall:
    """Tests for tools/call method."""

    async def test_tools_call_via_http(self, http_client: httpx.AsyncClient):
        """tools/call method invokes tool and returns result."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "nudge_list_components",
                    "arguments": {}
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        result = data["result"]
        # tools/call returns content array
        assert "content" in result
        assert isinstance(result["content"], list)

    async def test_tools_call_set_and_get(self, http_client: httpx.AsyncClient):
        """tools/call can set and get hints."""
        # Set a hint via tools/call
        set_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "nudge_set_hint",
                    "arguments": {
                        "component": "test-tools-call",
                        "key": "mykey",
                        "value": "myvalue"
                    }
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert set_response.status_code == 200
        set_data = set_response.json()
        assert "result" in set_data

        # Get the hint via tools/call
        get_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "nudge_get_hint",
                    "arguments": {
                        "component": "test-tools-call",
                        "key": "mykey"
                    }
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert get_response.status_code == 200
        get_data = get_response.json()
        assert "result" in get_data

    async def test_tools_call_unknown_tool_returns_error(self, http_client: httpx.AsyncClient):
        """tools/call with unknown tool returns error."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "nonexistent_tool",
                    "arguments": {}
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        # Should have error in result
        assert "result" in data
        result = data["result"]
        # Check for isError flag or error content
        assert result.get("isError", False) or "error" in str(result).lower()


class TestPing:
    """Tests for ping method."""

    async def test_ping_method(self, http_client: httpx.AsyncClient):
        """ping method returns empty result."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "ping",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        # Ping returns empty object
        assert data["result"] == {}


class TestInitializeHandshake:
    """Tests for full initialize handshake."""

    async def test_full_initialize_handshake(self, http_client: httpx.AsyncClient):
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
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
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
        assert "protocolVersion" in init_data["result"]
        assert "capabilities" in init_data["result"]

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

        # Should be 202 for notification
        assert initialized_response.status_code == 202

        # Step 3: tools/list
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
