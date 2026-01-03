"""Tests for blob CLI commands."""

import base64
import json
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestBlobUploadCommand:
    """Tests for nudge blob-upload command."""

    async def test_blob_upload_via_http(self, http_client):
        """Upload blob using direct HTTP (simulating CLI)."""
        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test file content for upload")
            temp_path = f.name

        try:
            # Read and upload via HTTP
            with open(temp_path, "rb") as f:
                data = f.read()

            response = await http_client.post(
                "/blobs",
                content=data,
                headers={
                    "Content-Type": "text/plain",
                    "Content-Disposition": 'attachment; filename="test.txt"',
                },
            )

            assert response.status_code == 201
            result = response.json()
            assert "blob_id" in result
            assert result["size"] == len(data)
        finally:
            Path(temp_path).unlink()

    async def test_blob_upload_with_content_type(self, http_client):
        """Upload blob with specific content type."""
        data = b'{"test": "json data"}'

        response = await http_client.post(
            "/blobs",
            content=data,
            headers={
                "Content-Type": "application/json",
                "Content-Disposition": 'attachment; filename="data.json"',
            },
        )

        assert response.status_code == 201
        result = response.json()
        assert result["content_type"] == "application/json"


class TestBlobDownloadCommand:
    """Tests for nudge blob-download command."""

    async def test_blob_download_via_http(self, http_client):
        """Download blob using direct HTTP (simulating CLI)."""
        # First upload
        original = b"Download test content"
        upload_response = await http_client.post(
            "/blobs",
            content=original,
            headers={"Content-Type": "text/plain"},
        )
        blob_id = upload_response.json()["blob_id"]

        # Then download
        response = await http_client.get(f"/blobs/{blob_id}")

        assert response.status_code == 200
        assert response.content == original

    async def test_blob_download_to_file(self, http_client):
        """Download blob to file (simulating -o option)."""
        original = b"Content to save to file"
        upload_response = await http_client.post(
            "/blobs",
            content=original,
            headers={"Content-Type": "application/octet-stream"},
        )
        blob_id = upload_response.json()["blob_id"]

        # Download
        response = await http_client.get(f"/blobs/{blob_id}")

        # Simulate writing to file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(response.content)
            temp_path = f.name

        try:
            with open(temp_path, "rb") as f:
                content = f.read()
            assert content == original
        finally:
            Path(temp_path).unlink()


class TestBlobListCommand:
    """Tests for nudge blob-list command."""

    async def test_blob_list_via_http(self, http_client):
        """List blobs using direct HTTP (simulating CLI)."""
        # Upload a few blobs
        for i in range(3):
            await http_client.post(
                "/blobs",
                content=f"blob {i}".encode(),
                headers={
                    "Content-Type": "text/plain",
                    "Content-Disposition": f'attachment; filename="file{i}.txt"',
                },
            )

        # List
        response = await http_client.get("/blobs")

        assert response.status_code == 200
        result = response.json()
        assert "blobs" in result
        assert len(result["blobs"]) >= 3


class TestBlobDeleteCommand:
    """Tests for nudge blob-delete command."""

    async def test_blob_delete_via_http(self, http_client):
        """Delete blob using direct HTTP (simulating CLI)."""
        # Upload
        upload_response = await http_client.post(
            "/blobs",
            content=b"to be deleted",
            headers={"Content-Type": "text/plain"},
        )
        blob_id = upload_response.json()["blob_id"]

        # Delete
        response = await http_client.delete(f"/blobs/{blob_id}")

        assert response.status_code == 204

        # Verify gone
        get_response = await http_client.get(f"/blobs/{blob_id}")
        assert get_response.status_code == 404


class TestBlobInfoCommand:
    """Tests for nudge blob-info command."""

    async def test_blob_info_via_mcp(self, http_client):
        """Get blob info via MCP tool (simulating CLI)."""
        # Upload
        data = b"Info test content"
        data_b64 = base64.b64encode(data).decode("ascii")

        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": data_b64,
                    "filename": "info-test.txt",
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
        info = result["result"]
        assert info["blob_id"] == blob_id
        assert info["filename"] == "info-test.txt"
        assert info["size"] == len(data)
        assert "checksum" in info
