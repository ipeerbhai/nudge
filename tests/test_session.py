"""Tests for MCP session management."""

import pytest
import httpx
import time


class TestSessionCreation:
    """Tests for session creation during initialize."""

    async def test_session_stored_after_initialize(self, http_client: httpx.AsyncClient):
        """Initialize creates a tracked session that can be used for subsequent requests."""
        # First, initialize to get a session
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
        assert session_id is not None

        # Now use that session for a tool call
        tool_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        # Should succeed
        assert tool_response.status_code == 200
        data = tool_response.json()
        assert "result" in data

    async def test_multiple_sessions_independent(self, http_client: httpx.AsyncClient):
        """Each initialize creates an independent session."""
        # Create first session
        resp1 = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "client1", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )
        session1 = resp1.headers.get("Mcp-Session-Id")

        # Create second session
        resp2 = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "client2", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )
        session2 = resp2.headers.get("Mcp-Session-Id")

        # Sessions should be different
        assert session1 != session2


class TestLegacyMode:
    """Tests for legacy mode (no session required)."""

    async def test_legacy_mode_works_without_session(self, http_client: httpx.AsyncClient):
        """Tool calls work without any session header (legacy mode)."""
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
        assert "result" in data

    async def test_legacy_mode_can_set_and_get_hints(self, http_client: httpx.AsyncClient):
        """Full workflow works without sessions."""
        # Set a hint
        set_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_set_hint",
                "params": {
                    "component": "test-legacy",
                    "key": "test-key",
                    "value": "test-value"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert set_response.status_code == 200
        assert "result" in set_response.json()

        # Get the hint back
        get_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_get_hint",
                "params": {
                    "component": "test-legacy",
                    "key": "test-key"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert "result" in data
        assert data["result"]["hint"]["value"] == "test-value"


class TestSessionExpiry:
    """Tests for session expiration handling."""

    async def test_expired_session_returns_404(self, http_client: httpx.AsyncClient):
        """Requests with expired/invalid session ID return 404."""
        # Use a fake session ID that doesn't exist
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
                "Mcp-Session-Id": "invalid-session-id-that-does-not-exist",
            }
        )

        # Should return 404 for unknown session
        # Note: In legacy mode, missing session is OK, but invalid session should be 404
        assert response.status_code == 404

    async def test_no_session_header_uses_legacy_mode(self, http_client: httpx.AsyncClient):
        """Request without Mcp-Session-Id header uses legacy mode (not 404)."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={"Content-Type": "application/json"}
            # Note: No Mcp-Session-Id header
        )

        # Should NOT be 404 - legacy mode should work
        assert response.status_code == 200
