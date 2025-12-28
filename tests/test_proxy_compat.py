"""Tests for PROXY mode compatibility with updated PRIMARY server."""

import pytest
import httpx


class TestLegacyClientCompat:
    """Tests for backward compatibility with legacy NudgeClient (no sessions)."""

    async def test_legacy_client_still_works(self, http_client: httpx.AsyncClient):
        """NudgeClient without session headers still works."""
        # Simulate legacy client behavior - no session headers at all
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_set_hint",
                "params": {
                    "component": "legacy-test",
                    "key": "test-key",
                    "value": "test-value"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        # Legacy get also works
        get_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_get_hint",
                "params": {
                    "component": "legacy-test",
                    "key": "test-key"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert get_response.status_code == 200
        get_data = get_response.json()
        assert "result" in get_data
        assert get_data["result"]["hint"]["value"] == "test-value"

    async def test_direct_tool_methods_work(self, http_client: httpx.AsyncClient):
        """Direct nudge_* method calls work without tools/call wrapper."""
        # This is how the legacy proxy forwards requests
        for method in ["nudge_list_components", "nudge_export"]:
            response = await http_client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": {}
                },
                headers={"Content-Type": "application/json"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "result" in data


class TestSessionAwareClient:
    """Tests for session-aware client behavior."""

    async def test_client_with_session_support(self, http_client: httpx.AsyncClient):
        """Updated client can use sessions for better tracking."""
        # Initialize to get session
        init_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "updated-client", "version": "2.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        session_id = init_response.headers.get("Mcp-Session-Id")
        assert session_id is not None

        # Use session for subsequent requests
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
                "Mcp-Session-Id": session_id,
            }
        )

        assert response.status_code == 200
        # Session should be echoed back
        assert response.headers.get("Mcp-Session-Id") == session_id


class TestMixedClients:
    """Tests for mixed legacy and session-aware clients."""

    async def test_mixed_clients_share_store(self, http_client: httpx.AsyncClient):
        """Legacy and session-aware clients can share the same store."""
        # Session-aware client sets a hint
        init_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "session-client", "version": "1.0"}
                }
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )
        session_id = init_response.headers.get("Mcp-Session-Id")

        await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_set_hint",
                "params": {
                    "component": "shared-store",
                    "key": "session-key",
                    "value": "session-value"
                }
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        # Legacy client can read it
        get_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "nudge_get_hint",
                "params": {
                    "component": "shared-store",
                    "key": "session-key"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["result"]["hint"]["value"] == "session-value"

        # Legacy client sets a hint
        await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "nudge_set_hint",
                "params": {
                    "component": "shared-store",
                    "key": "legacy-key",
                    "value": "legacy-value"
                }
            },
            headers={"Content-Type": "application/json"}
        )

        # Session-aware client can read it
        get_response2 = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "nudge_get_hint",
                "params": {
                    "component": "shared-store",
                    "key": "legacy-key"
                }
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session_id,
            }
        )

        assert get_response2.status_code == 200
        data2 = get_response2.json()
        assert data2["result"]["hint"]["value"] == "legacy-value"
