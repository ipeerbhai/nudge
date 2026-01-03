"""Binary blob storage for Nudge."""

import hashlib
import mimetypes
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterator, List, Optional, Tuple

from .models import ErrorCode


class BlobStoreError(Exception):
    """Error from blob store operations."""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class BlobMetadata:
    """Metadata for a stored blob."""

    blob_id: str
    filename: Optional[str]
    content_type: str
    size: int
    created_at: str
    session_id: Optional[str]
    checksum: str  # SHA-256 hex


# Magic byte signatures for content type detection
MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/zip",
    b"RIFF": "audio/wav",  # WAV files start with RIFF
    b"ID3": "audio/mpeg",  # MP3 with ID3 tag
    b"\xff\xfb": "audio/mpeg",  # MP3 without ID3 tag
    b"OggS": "audio/ogg",
}


def detect_content_type(filename: Optional[str], data: bytes) -> str:
    """
    Detect content type from filename extension or magic bytes.

    Args:
        filename: Optional filename with extension
        data: Binary data to inspect

    Returns:
        MIME type string
    """
    # Try magic bytes first for accuracy
    for magic, mime_type in MAGIC_BYTES.items():
        if data.startswith(magic):
            return mime_type

    # Fall back to filename extension
    if filename:
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type

    return "application/octet-stream"


class BlobStore:
    """In-memory binary blob storage."""

    MAX_BLOB_SIZE = 100 * 1024 * 1024  # 100 MB per blob
    MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB total
    MAX_BLOBS = 100  # Maximum number of blobs

    def __init__(self):
        """Initialize empty blob store."""
        self._blobs: Dict[str, bytes] = {}
        self._metadata: Dict[str, BlobMetadata] = {}
        self._total_size: int = 0

    def _generate_id(self) -> str:
        """Generate a unique blob ID."""
        return secrets.token_urlsafe(16)

    def _compute_checksum(self, data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()

    def upload(
        self,
        data: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> BlobMetadata:
        """
        Upload a new blob.

        Args:
            data: Binary blob data
            filename: Optional original filename
            content_type: Optional MIME type (auto-detected if not provided)
            session_id: Optional session ID for session-scoped blobs

        Returns:
            BlobMetadata with blob ID and other info

        Raises:
            BlobStoreError: If blob is too large or quota exceeded
        """
        # Check size limit
        if len(data) > self.MAX_BLOB_SIZE:
            raise BlobStoreError(
                ErrorCode.E_BLOB_TOO_LARGE,
                f"Blob size {len(data)} exceeds maximum of {self.MAX_BLOB_SIZE} bytes",
            )

        # Check total quota
        if self._total_size + len(data) > self.MAX_TOTAL_SIZE:
            raise BlobStoreError(
                ErrorCode.E_BLOB_QUOTA,
                f"Total blob storage would exceed quota of {self.MAX_TOTAL_SIZE} bytes",
            )

        # Check blob count
        if len(self._blobs) >= self.MAX_BLOBS:
            raise BlobStoreError(
                ErrorCode.E_BLOB_QUOTA,
                f"Maximum blob count of {self.MAX_BLOBS} exceeded",
            )

        # Auto-detect content type if not provided
        if content_type is None:
            content_type = detect_content_type(filename, data)

        # Generate ID and checksum
        blob_id = self._generate_id()
        checksum = self._compute_checksum(data)

        # Create metadata
        metadata = BlobMetadata(
            blob_id=blob_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            created_at=datetime.utcnow().isoformat(),
            session_id=session_id,
            checksum=checksum,
        )

        # Store blob and metadata
        self._blobs[blob_id] = data
        self._metadata[blob_id] = metadata
        self._total_size += len(data)

        return metadata

    def upload_with_id(
        self,
        blob_id: str,
        data: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        session_id: Optional[str] = None,
        checksum: Optional[str] = None,
    ) -> BlobMetadata:
        """
        Upload a blob with a specific ID (for import).

        Args:
            blob_id: Specific blob ID to use
            data: Binary blob data
            filename: Optional original filename
            content_type: Optional MIME type
            session_id: Optional session ID
            checksum: Optional checksum (computed if not provided)

        Returns:
            BlobMetadata

        Raises:
            BlobStoreError: If blob is too large or quota exceeded
        """
        # Check size limit
        if len(data) > self.MAX_BLOB_SIZE:
            raise BlobStoreError(
                ErrorCode.E_BLOB_TOO_LARGE,
                f"Blob size {len(data)} exceeds maximum of {self.MAX_BLOB_SIZE} bytes",
            )

        # Check total quota
        if self._total_size + len(data) > self.MAX_TOTAL_SIZE:
            raise BlobStoreError(
                ErrorCode.E_BLOB_QUOTA,
                f"Total blob storage would exceed quota of {self.MAX_TOTAL_SIZE} bytes",
            )

        # Auto-detect content type if not provided
        if content_type is None:
            content_type = detect_content_type(filename, data)

        # Compute checksum if not provided
        if checksum is None:
            checksum = self._compute_checksum(data)

        # Create metadata
        metadata = BlobMetadata(
            blob_id=blob_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            created_at=datetime.utcnow().isoformat(),
            session_id=session_id,
            checksum=checksum,
        )

        # Store blob and metadata
        self._blobs[blob_id] = data
        self._metadata[blob_id] = metadata
        self._total_size += len(data)

        return metadata

    def download(self, blob_id: str) -> Optional[Tuple[bytes, BlobMetadata]]:
        """
        Download a blob by ID.

        Args:
            blob_id: Blob ID to download

        Returns:
            Tuple of (data, metadata) or None if not found
        """
        if blob_id not in self._blobs:
            return None

        return self._blobs[blob_id], self._metadata[blob_id]

    def delete(self, blob_id: str) -> bool:
        """
        Delete a blob by ID.

        Args:
            blob_id: Blob ID to delete

        Returns:
            True if deleted, False if not found
        """
        if blob_id not in self._blobs:
            return False

        data = self._blobs.pop(blob_id)
        self._metadata.pop(blob_id)
        self._total_size -= len(data)

        return True

    def list_blobs(self, session_id: Optional[str] = None) -> List[BlobMetadata]:
        """
        List all blobs, optionally filtered by session.

        Args:
            session_id: If provided, only return blobs for this session.
                        If None, returns all blobs.

        Returns:
            List of BlobMetadata
        """
        if session_id is None:
            return list(self._metadata.values())

        return [m for m in self._metadata.values() if m.session_id == session_id]

    def get_metadata(self, blob_id: str) -> Optional[BlobMetadata]:
        """
        Get metadata for a blob without downloading data.

        Args:
            blob_id: Blob ID

        Returns:
            BlobMetadata or None if not found
        """
        return self._metadata.get(blob_id)

    def cleanup_session_blobs(self, session_id: str) -> int:
        """
        Remove all blobs for a session.

        Args:
            session_id: Session ID to clean up

        Returns:
            Number of blobs removed
        """
        to_delete = [
            blob_id
            for blob_id, meta in self._metadata.items()
            if meta.session_id == session_id
        ]

        for blob_id in to_delete:
            self.delete(blob_id)

        return len(to_delete)

    def export_all(self) -> Iterator[Tuple[str, bytes, BlobMetadata]]:
        """
        Export all blobs for backup/transfer.

        Yields:
            Tuples of (blob_id, data, metadata)
        """
        for blob_id, data in self._blobs.items():
            yield blob_id, data, self._metadata[blob_id]

    @property
    def total_size(self) -> int:
        """Get total size of all stored blobs."""
        return self._total_size

    @property
    def blob_count(self) -> int:
        """Get number of stored blobs."""
        return len(self._blobs)
