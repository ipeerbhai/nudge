"""Tests for blob MCP tools."""

import base64
import pytest
import httpx


class TestBlobToolsViaMCP:
    """Tests for blob tools via JSON-RPC."""

    async def test_blob_upload_tool(self, http_client: httpx.AsyncClient):
        """nudge_blob_upload tool accepts base64 data."""
        data = b"Hello from MCP tool!"
        data_b64 = base64.b64encode(data).decode("ascii")

        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": data_b64,
                    "filename": "hello.txt",
                    "content_type": "text/plain",
                },
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert "blob_id" in result["result"]
        assert result["result"]["size"] == len(data)

    async def test_blob_download_tool(self, http_client: httpx.AsyncClient):
        """nudge_blob_download returns base64 data."""
        # First upload
        original = b"Download me via MCP!"
        data_b64 = base64.b64encode(original).decode("ascii")

        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": data_b64,
                    "filename": "download.txt",
                },
            },
            headers={"Content-Type": "application/json"},
        )
        blob_id = upload_response.json()["result"]["blob_id"]

        # Then download
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_blob_download",
                "params": {"blob_id": blob_id},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert "data" in result["result"]

        downloaded = base64.b64decode(result["result"]["data"])
        assert downloaded == original

    async def test_blob_list_tool(self, http_client: httpx.AsyncClient):
        """nudge_blob_list returns blob metadata."""
        # Upload a blob first
        await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": base64.b64encode(b"list test").decode("ascii"),
                    "filename": "list-test.txt",
                },
            },
            headers={"Content-Type": "application/json"},
        )

        # List blobs
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_blob_list",
                "params": {},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert "blobs" in result["result"]
        assert len(result["result"]["blobs"]) > 0

    async def test_blob_delete_tool(self, http_client: httpx.AsyncClient):
        """nudge_blob_delete removes blob."""
        # Upload
        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": base64.b64encode(b"delete me").decode("ascii"),
                    "filename": "delete.txt",
                },
            },
            headers={"Content-Type": "application/json"},
        )
        blob_id = upload_response.json()["result"]["blob_id"]

        # Delete
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_blob_delete",
                "params": {"blob_id": blob_id},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert result["result"]["deleted"] is True

        # Verify it's gone
        download_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "nudge_blob_download",
                "params": {"blob_id": blob_id},
            },
            headers={"Content-Type": "application/json"},
        )

        assert "error" in download_response.json()

    async def test_blob_info_tool(self, http_client: httpx.AsyncClient):
        """nudge_blob_info returns metadata without downloading."""
        # Upload
        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": base64.b64encode(b"info test data").decode("ascii"),
                    "filename": "info.txt",
                    "content_type": "text/plain",
                },
            },
            headers={"Content-Type": "application/json"},
        )
        blob_id = upload_response.json()["result"]["blob_id"]

        # Get info
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_blob_info",
                "params": {"blob_id": blob_id},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert result["result"]["blob_id"] == blob_id
        assert result["result"]["filename"] == "info.txt"
        assert result["result"]["content_type"] == "text/plain"
        # Should NOT include data field
        assert "data" not in result["result"]


class TestBlobHintIntegration:
    """Tests for blob references in hints."""

    async def test_hint_with_blob_reference(self, http_client: httpx.AsyncClient):
        """Hint can store BlobReference value."""
        # First upload a blob
        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": base64.b64encode(b"\x89PNG fake image").decode("ascii"),
                    "filename": "image.png",
                    "content_type": "image/png",
                },
            },
            headers={"Content-Type": "application/json"},
        )
        blob_id = upload_response.json()["result"]["blob_id"]

        # Set a hint with blob reference
        set_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_set_hint",
                "params": {
                    "component": "screenshots",
                    "key": "error-dialog",
                    "value": {
                        "type": "blob_ref",
                        "blob_id": blob_id,
                        "content_type": "image/png",
                    },
                },
            },
            headers={"Content-Type": "application/json"},
        )
        assert set_response.status_code == 200

        # Get the hint back
        get_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "nudge_get_hint",
                "params": {
                    "component": "screenshots",
                    "key": "error-dialog",
                },
            },
            headers={"Content-Type": "application/json"},
        )

        assert get_response.status_code == 200
        result = get_response.json()
        hint_value = result["result"]["hint"]["value"]
        assert hint_value["type"] == "blob_ref"
        assert hint_value["blob_id"] == blob_id
