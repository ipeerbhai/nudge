"""Server-Sent Events (SSE) support for Nudge HTTP server."""

import json
from typing import Any, Optional
import uuid


class SSEWriter:
    """Formats and writes Server-Sent Events."""

    def __init__(self):
        """Initialize SSE writer with event counter."""
        self._event_counter = 0

    def generate_event_id(self) -> str:
        """Generate a unique event ID."""
        self._event_counter += 1
        return f"{uuid.uuid4().hex[:8]}-{self._event_counter}"

    def format_event(
        self,
        data: Any,
        event_type: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> bytes:
        """
        Format data as an SSE event.

        Args:
            data: The data to include in the event (will be JSON encoded if not a string)
            event_type: Optional event type (e.g., "message", "error")
            event_id: Optional event ID for resumability

        Returns:
            Bytes representing the formatted SSE event
        """
        lines = []

        # Event ID (optional, for resumability)
        if event_id:
            lines.append(f"id: {event_id}")

        # Event type (optional)
        if event_type:
            lines.append(f"event: {event_type}")

        # Data (required)
        if isinstance(data, str):
            data_str = data
        else:
            data_str = json.dumps(data)

        # SSE requires each line of data to be prefixed with "data: "
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")

        # Events are terminated by a blank line
        lines.append("")
        lines.append("")

        return "\n".join(lines).encode("utf-8")

    def format_comment(self, comment: str) -> bytes:
        """
        Format a comment (for keep-alive pings).

        Args:
            comment: The comment text

        Returns:
            Bytes representing the SSE comment
        """
        return f": {comment}\n".encode("utf-8")

    def format_retry(self, milliseconds: int) -> bytes:
        """
        Format a retry directive.

        Args:
            milliseconds: Reconnection time in milliseconds

        Returns:
            Bytes representing the retry directive
        """
        return f"retry: {milliseconds}\n\n".encode("utf-8")


def format_sse_event(
    data: Any,
    event_type: Optional[str] = None,
    event_id: Optional[str] = None,
) -> bytes:
    """
    Convenience function to format a single SSE event.

    Args:
        data: The data to include in the event
        event_type: Optional event type
        event_id: Optional event ID

    Returns:
        Bytes representing the formatted SSE event
    """
    writer = SSEWriter()
    return writer.format_event(data, event_type, event_id)
