"""HTTP JSON-RPC server for Nudge with MCP Streamable HTTP support."""

import json
import asyncio
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional, Tuple
import logging

from .session import SessionManager, Session

logger = logging.getLogger("nudge")

# MCP Protocol version
MCP_PROTOCOL_VERSION = "2025-06-18"

# Allowed Origin patterns for localhost
ALLOWED_ORIGINS = {
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
}


def is_origin_allowed(origin: Optional[str]) -> bool:
    """
    Check if an Origin header value is allowed.

    Allows:
    - No Origin header (non-browser requests)
    - localhost and 127.0.0.1 with any port
    """
    if origin is None:
        return True  # No Origin header is OK (non-browser requests)

    # Check exact matches first
    if origin in ALLOWED_ORIGINS:
        return True

    # Check with port suffix
    for allowed in ALLOWED_ORIGINS:
        if origin.startswith(allowed + ":"):
            return True

    return False


class JSONRPCHandler(BaseHTTPRequestHandler):
    """HTTP request handler for JSON-RPC with MCP session support."""

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    def _validate_origin(self) -> bool:
        """Validate Origin header. Returns False if request should be rejected."""
        origin = self.headers.get("Origin")
        if not is_origin_allowed(origin):
            self.send_error(403, "Forbidden: Invalid Origin")
            return False
        return True

    def _get_session_id(self) -> Optional[str]:
        """Get session ID from request headers."""
        return self.headers.get("Mcp-Session-Id")

    def _validate_session(self, session_id: Optional[str]) -> Tuple[bool, Optional[Session]]:
        """
        Validate session ID if present.

        Returns:
            Tuple of (is_valid, session)
            - If no session_id provided: (True, None) - legacy mode
            - If valid session_id: (True, session)
            - If invalid session_id: (False, None)
        """
        if session_id is None:
            # No session header = legacy mode, allow
            return True, None

        session_mgr = self.server.session_manager
        session = session_mgr.get_session(session_id)

        if session is None:
            # Session ID provided but not found/expired
            return False, None

        return True, session

    def _send_json_response(
        self,
        data: Dict,
        status: int = 200,
        session_id: Optional[str] = None
    ):
        """Send a JSON response with appropriate headers."""
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("MCP-Protocol-Version", MCP_PROTOCOL_VERSION)

        if session_id:
            self.send_header("Mcp-Session-Id", session_id)

        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """Handle POST requests."""
        try:
            # Validate Origin header (security)
            if not self._validate_origin():
                return

            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            request = json.loads(body)

            # Get session ID from header
            session_id = self._get_session_id()

            # Check if this is a batch request (array)
            if isinstance(request, list):
                self._handle_batch_request(request, session_id)
            else:
                self._handle_single_request(request, session_id)

        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            logger.exception("Error handling request")
            self.send_error(500, str(e))

    def _handle_single_request(self, request: Dict, session_id: Optional[str]):
        """Handle a single JSON-RPC request."""
        # Check if this is an initialize request (doesn't need session)
        method = request.get("method", "")
        is_initialize = method == "initialize"

        # Validate session (skip for initialize)
        if not is_initialize:
            is_valid, session = self._validate_session(session_id)
            if not is_valid:
                # Invalid session ID - return 404
                self.send_error(404, "Session not found")
                return
        else:
            session = None

        # Get handlers from server
        rpc_handler = self.server.rpc_handler
        session_mgr = self.server.session_manager

        # Call handler (it's async, so we need to run it)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # For initialize, we need to create a session and include it in the response
        if is_initialize:
            # Extract client info from params
            params = request.get("params", {})
            client_info = params.get("clientInfo")
            protocol_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)

            # Create session
            session = session_mgr.create_session(
                client_info=client_info,
                protocol_version=protocol_version
            )
            session_id = session.session_id

        # Call the RPC handler
        response = loop.run_until_complete(rpc_handler(request))
        loop.close()

        # Check if this is a notification (no id field)
        is_notification = "id" not in request

        if is_notification:
            # Notifications get 202 Accepted with no body
            self.send_response(202)
            self.send_header("MCP-Protocol-Version", MCP_PROTOCOL_VERSION)
            if session_id:
                self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
        else:
            # Requests get 200 OK with JSON body
            self._send_json_response(response, session_id=session_id)

    def _handle_batch_request(self, requests: list, session_id: Optional[str]):
        """Handle a batch of JSON-RPC requests."""
        # Empty batch is an error
        if len(requests) == 0:
            self.send_error(400, "Empty batch")
            return

        # Validate session once for the batch (if provided)
        if session_id:
            is_valid, session = self._validate_session(session_id)
            if not is_valid:
                self.send_error(404, "Session not found")
                return

        rpc_handler = self.server.rpc_handler
        session_mgr = self.server.session_manager

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        responses = []
        all_notifications = True

        for request in requests:
            if not isinstance(request, dict):
                # Invalid request in batch
                continue

            method = request.get("method", "")
            is_initialize = method == "initialize"
            has_id = "id" in request

            if has_id:
                all_notifications = False

            # Handle initialize specially
            if is_initialize:
                params = request.get("params", {})
                client_info = params.get("clientInfo")
                protocol_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
                session = session_mgr.create_session(
                    client_info=client_info,
                    protocol_version=protocol_version
                )
                session_id = session.session_id

            # Call handler
            response = loop.run_until_complete(rpc_handler(request))

            # Only include response for requests (not notifications)
            if has_id:
                responses.append(response)

        loop.close()

        if all_notifications:
            # All notifications - return 202
            self.send_response(202)
            self.send_header("MCP-Protocol-Version", MCP_PROTOCOL_VERSION)
            if session_id:
                self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
        else:
            # Has at least one request - return array of responses
            self._send_json_response(responses, session_id=session_id)

    def do_GET(self):
        """Handle GET requests (health check and SSE streams)."""
        if self.path == "/health":
            response = {
                "status": "ok",
                "pid": os.getpid()
            }
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/" or self.path == "":
            # MCP endpoint - check if SSE is requested
            accept = self.headers.get("Accept", "")

            if "text/event-stream" in accept:
                # SSE stream requested - open stream
                self._handle_sse_stream()
            else:
                # GET without SSE Accept header - Method Not Allowed
                self.send_error(405, "Method Not Allowed: Use Accept: text/event-stream for SSE")
        else:
            self.send_error(404, "Not Found")

    def _handle_sse_stream(self):
        """Handle SSE stream for server-to-client messages."""
        from .sse import SSEWriter

        # Validate session if present
        session_id = self._get_session_id()
        if session_id:
            is_valid, session = self._validate_session(session_id)
            if not is_valid:
                self.send_error(404, "Session not found")
                return

        # Send SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("MCP-Protocol-Version", MCP_PROTOCOL_VERSION)

        if session_id:
            self.send_header("Mcp-Session-Id", session_id)

        self.end_headers()

        # For now, just send a connection established comment and close
        # In a full implementation, this would be a long-lived stream
        writer = SSEWriter()
        self.wfile.write(writer.format_comment("connected"))
        self.wfile.flush()

    def do_DELETE(self):
        """Handle DELETE requests for session termination."""
        # Only handle the MCP endpoint
        if self.path != "/" and self.path != "":
            self.send_error(404, "Not Found")
            return

        # Session ID is required for DELETE
        session_id = self._get_session_id()
        if not session_id:
            self.send_error(400, "Bad Request: Mcp-Session-Id header required")
            return

        # Validate and terminate session
        session_mgr = self.server.session_manager
        session = session_mgr.get_session(session_id)

        if session is None:
            # Session doesn't exist or already terminated
            self.send_error(404, "Session not found")
            return

        # Terminate the session
        session_mgr.terminate_session(session_id)

        # Return 202 Accepted
        self.send_response(202)
        self.send_header("MCP-Protocol-Version", MCP_PROTOCOL_VERSION)
        self.end_headers()


class NudgeHTTPServer:
    """HTTP server for Nudge RPC with MCP session support."""

    def __init__(
        self,
        rpc_handler: Callable,
        port: int = 8765,
        session_manager: Optional[SessionManager] = None
    ):
        """
        Initialize HTTP server.

        Args:
            rpc_handler: Async function to handle RPC requests
            port: Port to bind to (will auto-increment if taken)
            session_manager: Optional session manager. If not provided, creates one.
        """
        self.rpc_handler = rpc_handler
        self.requested_port = port
        self.actual_port = None
        self.httpd = None
        self.session_manager = session_manager or SessionManager()

    def start(self) -> int:
        """
        Start the HTTP server.

        Returns:
            The actual port number used

        Raises:
            RuntimeError: If unable to bind to any port
        """
        port = self.requested_port
        max_attempts = 10

        for attempt in range(max_attempts):
            try:
                self.httpd = HTTPServer(("localhost", port), JSONRPCHandler)
                self.httpd.rpc_handler = self.rpc_handler
                self.httpd.session_manager = self.session_manager
                # Get actual port (important when port=0 is used for auto-assign)
                self.actual_port = self.httpd.server_address[1]
                logger.info(f"HTTP server bound to localhost:{self.actual_port}")
                return self.actual_port
            except OSError as e:
                if e.errno == 48 or e.errno == 98:  # Address already in use
                    logger.debug(f"Port {port} in use, trying {port + 1}")
                    port += 1
                else:
                    raise

        raise RuntimeError(f"Could not bind to any port from {self.requested_port} to {port}")

    async def serve_forever(self):
        """Serve HTTP requests forever (async)."""
        if not self.httpd:
            raise RuntimeError("Server not started. Call start() first.")

        # Run the blocking serve_forever in a thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.httpd.serve_forever)

    def stop(self):
        """Stop the HTTP server."""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
