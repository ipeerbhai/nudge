"""HTTP JSON-RPC server for Nudge."""

import json
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger("nudge")


class JSONRPCHandler(BaseHTTPRequestHandler):
    """HTTP request handler for JSON-RPC."""

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    def do_POST(self):
        """Handle POST requests."""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            request = json.loads(body)

            # Get the RPC handler from server
            handler = self.server.rpc_handler

            # Call handler (it's async, so we need to run it)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(handler(request))
            loop.close()

            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            logger.exception("Error handling request")
            self.send_error(500, str(e))

    def do_GET(self):
        """Handle GET requests (health check)."""
        if self.path == '/health':
            import os
            response = {
                "status": "ok",
                "pid": os.getpid()
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")


class NudgeHTTPServer:
    """HTTP server for Nudge RPC."""

    def __init__(self, rpc_handler: Callable, port: int = 8765):
        """
        Initialize HTTP server.

        Args:
            rpc_handler: Async function to handle RPC requests
            port: Port to bind to (will auto-increment if taken)
        """
        self.rpc_handler = rpc_handler
        self.requested_port = port
        self.actual_port = None
        self.httpd = None

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
                self.httpd = HTTPServer(('localhost', port), JSONRPCHandler)
                self.httpd.rpc_handler = self.rpc_handler
                self.actual_port = port
                logger.info(f"HTTP server bound to localhost:{port}")
                return port
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
