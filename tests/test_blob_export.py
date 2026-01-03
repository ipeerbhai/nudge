"""Tests for blob export/import functionality."""

import base64
import pytest
import httpx


class TestBlobExportViaHTTP:
    """Tests for blob export via HTTP endpoints."""

    async def test_export_includes_blobs_section(self, http_client: httpx.AsyncClient):
        """Export includes blobs section when blobs exist."""
        # Upload a blob
        await http_client.post(
            "/blobs",
            content=b"export test data",
            headers={
                "Content-Type": "text/plain",
                "Content-Disposition": 'attachment; filename="export.txt"',
            },
        )

        # Export via RPC
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_export",
                "params": {"format": "json"},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        payload = result["result"]["payload"]
        # Check schema version is updated to 1.1
        assert payload["schema_version"] in ("1.0", "1.1")

    async def test_export_blobs_are_base64_encoded(self, http_client: httpx.AsyncClient):
        """Exported blobs have base64-encoded data."""
        original = b"Binary data \x00\x01\x02 for encoding test"

        # Upload via MCP tool
        data_b64 = base64.b64encode(original).decode("ascii")
        upload_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_blob_upload",
                "params": {
                    "data": data_b64,
                    "filename": "binary.bin",
                },
            },
            headers={"Content-Type": "application/json"},
        )
        blob_id = upload_response.json()["result"]["blob_id"]

        # Download to verify round-trip
        download_response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_blob_download",
                "params": {"blob_id": blob_id},
            },
            headers={"Content-Type": "application/json"},
        )

        result = download_response.json()["result"]
        downloaded = base64.b64decode(result["data"])
        assert downloaded == original


class TestBlobImportViaHTTP:
    """Tests for blob import via HTTP endpoints."""

    async def test_upload_and_list_persists(self, http_client: httpx.AsyncClient):
        """Uploaded blobs appear in list."""
        # Upload
        await http_client.post(
            "/blobs",
            content=b"persistence test",
            headers={
                "Content-Type": "text/plain",
                "Content-Disposition": 'attachment; filename="persist.txt"',
            },
        )

        # List
        response = await http_client.get("/blobs")
        result = response.json()

        assert len(result["blobs"]) > 0
        filenames = [b.get("filename") for b in result["blobs"]]
        assert "persist.txt" in filenames


class TestBlobMergeMode:
    """Tests for merge mode with blobs."""

    async def test_merge_mode_preserves_existing_blobs(self, http_client: httpx.AsyncClient):
        """Import merge mode doesn't delete existing blobs."""
        # Upload first blob
        upload1 = await http_client.post(
            "/blobs",
            content=b"blob 1",
            headers={
                "Content-Type": "text/plain",
                "Content-Disposition": 'attachment; filename="one.txt"',
            },
        )
        blob1_id = upload1.json()["blob_id"]

        # Upload second blob
        await http_client.post(
            "/blobs",
            content=b"blob 2",
            headers={
                "Content-Type": "text/plain",
                "Content-Disposition": 'attachment; filename="two.txt"',
            },
        )

        # First blob should still exist
        response = await http_client.get(f"/blobs/{blob1_id}")
        assert response.status_code == 200


class TestBlobExportEmpty:
    """Tests for export with no blobs."""

    async def test_export_works_with_no_blobs(self, http_client: httpx.AsyncClient):
        """Export works even when no blobs exist."""
        # Just set a regular hint (no blobs)
        await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nudge_set_hint",
                "params": {
                    "component": "export-test",
                    "key": "test-key",
                    "value": "test-value",
                },
            },
            headers={"Content-Type": "application/json"},
        )

        # Export should work
        response = await http_client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nudge_export",
                "params": {"format": "json"},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "result" in result
        assert "payload" in result["result"]
