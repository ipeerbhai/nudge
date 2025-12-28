"""Tests for batch request handling."""

import pytest
import httpx


class TestBatchRequests:
    """Tests for JSON-RPC batch request handling."""

    async def test_batch_requests(self, http_client: httpx.AsyncClient):
        """Array of requests returns array of responses."""
        response = await http_client.post(
            "/",
            json=[
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "nudge_list_components",
                    "params": {}
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "ping",
                    "params": {}
                }
            ],
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should be an array of responses
        assert isinstance(data, list)
        assert len(data) == 2

        # Check both responses
        ids = [r.get("id") for r in data]
        assert 1 in ids
        assert 2 in ids

    async def test_batch_notifications(self, http_client: httpx.AsyncClient):
        """Array of notifications returns 202."""
        response = await http_client.post(
            "/",
            json=[
                {
                    "jsonrpc": "2.0",
                    "method": "initialized"
                    # No id = notification
                },
                {
                    "jsonrpc": "2.0",
                    "method": "initialized"
                }
            ],
            headers={"Content-Type": "application/json"}
        )

        # Batch of only notifications returns 202
        assert response.status_code == 202

    async def test_mixed_batch(self, http_client: httpx.AsyncClient):
        """Batch with requests and notifications handled correctly."""
        response = await http_client.post(
            "/",
            json=[
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "nudge_list_components",
                    "params": {}
                },
                {
                    "jsonrpc": "2.0",
                    "method": "initialized"
                    # Notification - no id
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "ping",
                    "params": {}
                }
            ],
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have responses for requests (not notifications)
        assert isinstance(data, list)
        # Notifications don't generate responses, only requests do
        assert len(data) == 2

        ids = [r.get("id") for r in data]
        assert 1 in ids
        assert 2 in ids

    async def test_batch_ordering_preserved(self, http_client: httpx.AsyncClient):
        """Response order matches request order."""
        response = await http_client.post(
            "/",
            json=[
                {
                    "jsonrpc": "2.0",
                    "id": "first",
                    "method": "nudge_list_components",
                    "params": {}
                },
                {
                    "jsonrpc": "2.0",
                    "id": "second",
                    "method": "ping",
                    "params": {}
                },
                {
                    "jsonrpc": "2.0",
                    "id": "third",
                    "method": "nudge_list_components",
                    "params": {}
                }
            ],
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) == 3

        # Verify order is preserved
        assert data[0]["id"] == "first"
        assert data[1]["id"] == "second"
        assert data[2]["id"] == "third"

    async def test_empty_batch_returns_error(self, http_client: httpx.AsyncClient):
        """Empty batch array returns error."""
        response = await http_client.post(
            "/",
            json=[],
            headers={"Content-Type": "application/json"}
        )

        # Empty batch should return error
        assert response.status_code == 400
