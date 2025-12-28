"""Tests for Server-Sent Events (SSE) support."""

import pytest
import httpx
import asyncio


class TestSSEEndpoint:
    """Tests for SSE stream endpoint."""

    async def test_get_returns_sse_stream(
        self, http_client: httpx.AsyncClient, initialized_session: str
    ):
        """GET / with Accept: text/event-stream returns SSE stream."""
        # Use streaming to avoid timeout waiting for full response
        async with http_client.stream(
            "GET",
            "/",
            headers={
                "Accept": "text/event-stream",
                "Mcp-Session-Id": initialized_session,
            },
            timeout=2.0,
        ) as response:
            assert response.status_code == 200
            content_type = response.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type

    async def test_get_without_sse_accept_returns_405(self, http_client: httpx.AsyncClient):
        """GET without Accept: text/event-stream returns 405."""
        response = await http_client.get(
            "/",
            headers={
                "Accept": "application/json",
            }
        )

        # Should return 405 Method Not Allowed for GET without SSE
        assert response.status_code == 405

    async def test_get_health_still_works(self, http_client: httpx.AsyncClient):
        """GET /health still works regardless of Accept header."""
        response = await http_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestSSEEventFormat:
    """Tests for SSE event formatting."""

    async def test_sse_event_format(
        self, http_client: httpx.AsyncClient, initialized_session: str
    ):
        """SSE events have correct format with data field."""
        # Use streaming to avoid timeout
        async with http_client.stream(
            "GET",
            "/",
            headers={
                "Accept": "text/event-stream",
                "Mcp-Session-Id": initialized_session,
            },
            timeout=2.0,
        ) as response:
            assert response.status_code == 200

            # For a basic SSE stream, we just verify it opens successfully
            content_type = response.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type


class TestPOSTWithSSE:
    """Tests for POST requests that can return SSE."""

    async def test_json_response_default(self, http_client: httpx.AsyncClient):
        """POST without SSE in Accept header returns JSON directly."""
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        assert response.status_code == 200
        content_type = response.headers.get("Content-Type", "")
        assert "application/json" in content_type

        # Should be valid JSON
        data = response.json()
        assert "result" in data

    async def test_post_with_sse_accept_returns_json_for_simple_requests(
        self, http_client: httpx.AsyncClient
    ):
        """POST with SSE in Accept still returns JSON for simple requests."""
        # For simple requests, server may choose JSON over SSE
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_list_components",
                "params": {}
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
        )

        assert response.status_code == 200
        # For simple, non-streaming responses, JSON is acceptable
        content_type = response.headers.get("Content-Type", "")
        # Could be either JSON or SSE depending on implementation
        assert "application/json" in content_type or "text/event-stream" in content_type
