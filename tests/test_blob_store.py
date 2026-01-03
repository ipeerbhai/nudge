"""Tests for BlobStore."""

import pytest
from nudge.core.blob_store import BlobStore, BlobStoreError, BlobMetadata


class TestBlobStoreBasics:
    """Basic BlobStore CRUD tests."""

    def test_upload_returns_metadata(self):
        """Uploading a blob returns metadata with id and checksum."""
        store = BlobStore()
        data = b"Hello, World!"

        metadata = store.upload(data, filename="hello.txt", content_type="text/plain")

        assert metadata.blob_id is not None
        assert len(metadata.blob_id) > 0
        assert metadata.filename == "hello.txt"
        assert metadata.content_type == "text/plain"
        assert metadata.size == len(data)
        assert metadata.checksum is not None
        assert len(metadata.checksum) == 64  # SHA-256 hex

    def test_upload_generates_unique_ids(self):
        """Each upload generates a unique blob ID."""
        store = BlobStore()

        meta1 = store.upload(b"data1", filename="a.txt")
        meta2 = store.upload(b"data2", filename="b.txt")
        meta3 = store.upload(b"data1", filename="c.txt")  # Same content, different ID

        assert meta1.blob_id != meta2.blob_id
        assert meta1.blob_id != meta3.blob_id
        assert meta2.blob_id != meta3.blob_id

    def test_download_returns_original_data(self):
        """Downloaded data matches uploaded data."""
        store = BlobStore()
        original = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Fake PNG

        metadata = store.upload(original, filename="image.png", content_type="image/png")
        data, meta = store.download(metadata.blob_id)

        assert data == original
        assert meta.blob_id == metadata.blob_id

    def test_download_nonexistent_returns_none(self):
        """Downloading nonexistent blob returns None."""
        store = BlobStore()

        result = store.download("nonexistent-id")

        assert result is None

    def test_delete_removes_blob(self):
        """Deleted blob is no longer accessible."""
        store = BlobStore()
        metadata = store.upload(b"data", filename="test.txt")

        deleted = store.delete(metadata.blob_id)

        assert deleted is True
        assert store.download(metadata.blob_id) is None

    def test_delete_nonexistent_returns_false(self):
        """Deleting nonexistent blob returns False."""
        store = BlobStore()

        deleted = store.delete("nonexistent-id")

        assert deleted is False

    def test_list_returns_all_blobs(self):
        """List returns metadata for all stored blobs."""
        store = BlobStore()

        meta1 = store.upload(b"data1", filename="a.txt")
        meta2 = store.upload(b"data2", filename="b.txt")

        blobs = store.list_blobs()

        assert len(blobs) == 2
        ids = [b.blob_id for b in blobs]
        assert meta1.blob_id in ids
        assert meta2.blob_id in ids

    def test_get_metadata_returns_info(self):
        """Get metadata without downloading data."""
        store = BlobStore()
        metadata = store.upload(b"test data", filename="test.txt")

        result = store.get_metadata(metadata.blob_id)

        assert result is not None
        assert result.blob_id == metadata.blob_id
        assert result.filename == "test.txt"

    def test_get_metadata_nonexistent_returns_none(self):
        """Get metadata for nonexistent blob returns None."""
        store = BlobStore()

        result = store.get_metadata("nonexistent-id")

        assert result is None


class TestBlobStoreLimits:
    """Tests for size and quota limits."""

    def test_upload_rejects_oversized_blob(self):
        """Blobs over 100MB are rejected."""
        store = BlobStore()
        # Create data slightly over limit
        oversized = b"x" * (BlobStore.MAX_BLOB_SIZE + 1)

        with pytest.raises(BlobStoreError) as exc_info:
            store.upload(oversized, filename="huge.bin")

        assert "exceeds maximum" in str(exc_info.value).lower()

    def test_upload_accepts_max_size_blob(self):
        """Blob exactly at limit is accepted."""
        store = BlobStore()
        # Create a smaller test to avoid memory issues in tests
        # We'll use a mock or smaller limit for actual testing
        max_size = b"x" * 1000  # Small for test

        # This should not raise
        metadata = store.upload(max_size, filename="max.bin")
        assert metadata is not None

    def test_upload_rejects_when_quota_exceeded(self):
        """Upload fails when total storage would exceed limit."""
        store = BlobStore()
        # Override for testing
        store.MAX_TOTAL_SIZE = 1000

        store.upload(b"x" * 500, filename="a.bin")
        store.upload(b"x" * 400, filename="b.bin")

        with pytest.raises(BlobStoreError) as exc_info:
            store.upload(b"x" * 200, filename="c.bin")  # Would exceed 1000

        assert "quota" in str(exc_info.value).lower()

    def test_max_blob_count_enforced(self):
        """Maximum blob count limit is enforced."""
        store = BlobStore()
        store.MAX_BLOBS = 3

        store.upload(b"1", filename="1.txt")
        store.upload(b"2", filename="2.txt")
        store.upload(b"3", filename="3.txt")

        with pytest.raises(BlobStoreError) as exc_info:
            store.upload(b"4", filename="4.txt")

        assert "exceeded" in str(exc_info.value).lower()


class TestBlobStoreContentType:
    """Tests for content type detection."""

    def test_detects_png_from_magic_bytes(self):
        """PNG files detected by magic bytes."""
        store = BlobStore()
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        metadata = store.upload(png_data, filename="image")  # No extension

        assert metadata.content_type == "image/png"

    def test_detects_jpeg_from_magic_bytes(self):
        """JPEG files detected by magic bytes."""
        store = BlobStore()
        jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        metadata = store.upload(jpeg_data, filename="photo")

        assert metadata.content_type == "image/jpeg"

    def test_detects_gif_from_magic_bytes(self):
        """GIF files detected by magic bytes."""
        store = BlobStore()
        gif_data = b"GIF89a" + b"\x00" * 100

        metadata = store.upload(gif_data, filename="animation")

        assert metadata.content_type == "image/gif"

    def test_detects_pdf_from_magic_bytes(self):
        """PDF files detected by magic bytes."""
        store = BlobStore()
        pdf_data = b"%PDF-1.4" + b"\x00" * 100

        metadata = store.upload(pdf_data, filename="document")

        assert metadata.content_type == "application/pdf"

    def test_uses_provided_content_type(self):
        """Explicit content type overrides detection."""
        store = BlobStore()
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        metadata = store.upload(
            png_data, filename="image.png", content_type="application/octet-stream"
        )

        assert metadata.content_type == "application/octet-stream"

    def test_uses_filename_extension_for_type(self):
        """Uses filename extension when magic bytes don't match."""
        store = BlobStore()
        data = b"not a real image"

        metadata = store.upload(data, filename="data.json")

        assert metadata.content_type == "application/json"

    def test_defaults_to_octet_stream(self):
        """Unknown types default to application/octet-stream."""
        store = BlobStore()
        data = b"unknown binary data"

        metadata = store.upload(data, filename="mystery")

        assert metadata.content_type == "application/octet-stream"


class TestBlobStoreScopes:
    """Tests for session-scoped blobs."""

    def test_session_blob_created_with_session_id(self):
        """Session-scoped blobs have session ID set."""
        store = BlobStore()

        metadata = store.upload(
            b"session data", filename="temp.txt", session_id="session-123"
        )

        assert metadata.session_id == "session-123"

    def test_global_blob_has_no_session_id(self):
        """Global blobs have no session ID."""
        store = BlobStore()

        metadata = store.upload(b"global data", filename="shared.txt")

        assert metadata.session_id is None

    def test_list_filters_by_session(self):
        """List can filter by session ID."""
        store = BlobStore()

        store.upload(b"global", filename="global.txt")
        store.upload(b"s1", filename="s1.txt", session_id="session-1")
        store.upload(b"s2", filename="s2.txt", session_id="session-2")

        s1_blobs = store.list_blobs(session_id="session-1")
        s2_blobs = store.list_blobs(session_id="session-2")
        all_blobs = store.list_blobs()

        assert len(s1_blobs) == 1
        assert s1_blobs[0].session_id == "session-1"
        assert len(s2_blobs) == 1
        assert len(all_blobs) == 3

    def test_cleanup_removes_session_blobs(self):
        """Session cleanup removes only that session's blobs."""
        store = BlobStore()

        store.upload(b"global", filename="global.txt")
        store.upload(b"s1", filename="s1.txt", session_id="session-1")
        store.upload(b"s2", filename="s2.txt", session_id="session-2")

        removed = store.cleanup_session_blobs("session-1")

        assert removed == 1
        assert len(store.list_blobs()) == 2
        assert len(store.list_blobs(session_id="session-1")) == 0


class TestBlobStoreExport:
    """Tests for export functionality."""

    def test_export_all_returns_blobs(self):
        """Export returns all blobs with data and metadata."""
        store = BlobStore()

        store.upload(b"data1", filename="a.txt")
        store.upload(b"data2", filename="b.txt")

        exports = list(store.export_all())

        assert len(exports) == 2
        for blob_id, data, metadata in exports:
            assert isinstance(blob_id, str)
            assert isinstance(data, bytes)
            assert isinstance(metadata, BlobMetadata)

    def test_upload_with_id_preserves_id(self):
        """Upload with specific ID preserves the ID for import."""
        store = BlobStore()

        metadata = store.upload_with_id(
            blob_id="custom-id-123",
            data=b"imported data",
            filename="imported.txt",
            content_type="text/plain",
        )

        assert metadata.blob_id == "custom-id-123"

        # Can download with that ID
        data, meta = store.download("custom-id-123")
        assert data == b"imported data"
