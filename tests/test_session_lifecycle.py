"""Tests for session lifecycle including DELETE and termination."""

import pytest
import httpx


class TestDeleteMethod:
    """Tests for DELETE method for session termination."""

    async def test_delete_terminates_session(
        self, http_client: httpx.AsyncClient, initialized_session: str
    ):
        """DELETE with valid session ID terminates session."""
        # First verify session works
        check_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": initialized_session,
            }
        )
        assert check_response.status_code == 200

        # Now terminate session with DELETE
        delete_response = await http_client.delete(
            "/",
            headers={
                "Mcp-Session-Id": initialized_session,
            }
        )

        # Should return 202 Accepted
        assert delete_response.status_code == 202

    async def test_terminated_session_returns_404(
        self, http_client: httpx.AsyncClient, initialized_session: str
    ):
        """Requests to terminated session return 404."""
        # Terminate the session
        delete_response = await http_client.delete(
            "/",
            headers={
                "Mcp-Session-Id": initialized_session,
            }
        )
        assert delete_response.status_code == 202

        # Now try to use the terminated session
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
                "Mcp-Session-Id": initialized_session,
            }
        )

        # Should return 404 for terminated session
        assert response.status_code == 404

    async def test_delete_requires_session_id(self, http_client: httpx.AsyncClient):
        """DELETE without session ID returns 400."""
        response = await http_client.delete("/")

        # Should return 400 Bad Request
        assert response.status_code == 400

    async def test_delete_invalid_session_returns_404(self, http_client: httpx.AsyncClient):
        """DELETE with unknown session ID returns 404."""
        response = await http_client.delete(
            "/",
            headers={
                "Mcp-Session-Id": "nonexistent-session-id",
            }
        )

        # Should return 404 Not Found
        assert response.status_code == 404


class TestSessionIsolation:
    """Tests for session isolation."""

    async def test_sessions_are_isolated(self, http_client: httpx.AsyncClient):
        """Terminating one session doesn't affect others."""
        # Create session 1
        init1 = await http_client.post(
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
        session1 = init1.headers.get("Mcp-Session-Id")

        # Create session 2
        init2 = await http_client.post(
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
        session2 = init2.headers.get("Mcp-Session-Id")

        # Terminate session 1
        await http_client.delete("/", headers={"Mcp-Session-Id": session1})

        # Session 2 should still work
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session2,
            }
        )
        assert response.status_code == 200

        # Session 1 should be terminated
        response1 = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session1,
            }
        )
        assert response1.status_code == 404
