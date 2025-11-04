"""MCP server implementation for Nudge."""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .core.store import Store, NudgeStoreError
from .core.models import (
    Hint,
    HintMeta,
    HintValue,
    NudgeContext,
    Scope,
    OS,
    ErrorCode,
    Sensitivity,
    CommandValue,
    PathValue,
    TemplateValue,
    JsonValue,
    ShellType,
    TemplateFormat,
)
from .core.scoring import Scorer
from .core.safety import SafetyGuard
from .http_server import NudgeHTTPServer
from .lock import ServerLock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nudge")


class NudgeServer:
    """MCP server for Nudge hint store."""

    def __init__(self):
        """Initialize the Nudge MCP server."""
        self.store = Store(
            max_components=int(os.getenv("NUDGE_MAX_HINTS", "5000")),
        )
        self.secret_guard_enabled = os.getenv("NUDGE_SECRET_GUARD", "1") == "1"
        self.server = Server("nudge")
        self.http_server = None
        self.lock = ServerLock()

        # Register tool handlers
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available Nudge tools."""
            return [
                Tool(
                    name="nudge.set_hint",
                    description="Set or update a hint in the store",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key", "value"],
                        "properties": {
                            "component": {"type": "string", "minLength": 1},
                            "key": {"type": "string", "minLength": 1},
                            "value": {},
                            "meta": {"type": "object"},
                            "if_match_version": {"type": "integer", "minimum": 0},
                        },
                    },
                ),
                Tool(
                    name="nudge.get_hint",
                    description="Get the best matching hint for a component and key",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                            "context": {"type": "object"},
                        },
                    },
                ),
                Tool(
                    name="nudge.query",
                    description="Search for hints by component, keys, tags, or regex",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "component": {"type": "string"},
                            "keys": {"type": "array", "items": {"type": "string"}},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "regex": {"type": "string"},
                            "context": {"type": "object"},
                            "limit": {"type": "integer", "minimum": 1, "default": 10},
                        },
                    },
                ),
                Tool(
                    name="nudge.delete_hint",
                    description="Delete a hint from the store",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="nudge.list_components",
                    description="List all components with hint counts",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="nudge.bump",
                    description="Increase frecency counter after successful hint use",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                            "delta": {"type": "integer", "minimum": 1, "default": 1},
                        },
                    },
                ),
                Tool(
                    name="nudge.export",
                    description="Export the entire store or subset",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "format": {"type": "string", "enum": ["json"], "default": "json"}
                        },
                    },
                ),
                Tool(
                    name="nudge.import",
                    description="Import hints from a payload",
                    inputSchema={
                        "type": "object",
                        "required": ["payload"],
                        "properties": {
                            "payload": {"type": "object"},
                            "mode": {"type": "string", "enum": ["merge", "replace"], "default": "merge"},
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> List[TextContent]:
            """Handle tool calls."""
            try:
                if name == "nudge.set_hint":
                    result = await self._handle_set_hint(arguments)
                elif name == "nudge.get_hint":
                    result = await self._handle_get_hint(arguments)
                elif name == "nudge.query":
                    result = await self._handle_query(arguments)
                elif name == "nudge.delete_hint":
                    result = await self._handle_delete_hint(arguments)
                elif name == "nudge.list_components":
                    result = await self._handle_list_components(arguments)
                elif name == "nudge.bump":
                    result = await self._handle_bump(arguments)
                elif name == "nudge.export":
                    result = await self._handle_export(arguments)
                elif name == "nudge.import":
                    result = await self._handle_import(arguments)
                else:
                    return [TextContent(type="text", text=json.dumps({"error": "Unknown tool"}))]

                return [TextContent(type="text", text=json.dumps(result))]

            except NudgeStoreError as e:
                error_response = {
                    "error": {
                        "code": e.code.value,
                        "message": e.message,
                        "data": e.data,
                    }
                }
                return [TextContent(type="text", text=json.dumps(error_response))]
            except Exception as e:
                logger.exception("Error handling tool call")
                error_response = {
                    "error": {
                        "code": ErrorCode.E_INVALID.value,
                        "message": str(e),
                        "data": {},
                    }
                }
                return [TextContent(type="text", text=json.dumps(error_response))]

    async def _handle_set_hint(self, args: Dict) -> Dict:
        """Handle set_hint tool call."""
        component = args["component"]
        key = args["key"]
        value = args["value"]
        meta_dict = args.get("meta", {})
        if_match_version = args.get("if_match_version")

        # Parse meta
        meta = self._parse_meta(meta_dict)

        # Validate with safety guard
        is_valid, error = SafetyGuard.validate_hint_value(
            value, meta.sensitivity, self.secret_guard_enabled
        )
        if not is_valid:
            raise NudgeStoreError(ErrorCode.E_SECRET_REJECTED, error)

        # Set the hint
        hint = self.store.set_hint(component, key, value, meta, if_match_version)

        return {"hint": self._hint_to_dict(component, key, hint)}

    async def _handle_get_hint(self, args: Dict) -> Dict:
        """Handle get_hint tool call."""
        component = args["component"]
        key = args["key"]
        context_dict = args.get("context", {})

        context = self._parse_context(context_dict)

        # Get hint
        hint = self.store.get_hint(component, key)
        if not hint:
            raise NudgeStoreError(
                ErrorCode.E_NOT_FOUND, f"Hint {component}/{key} not found"
            )

        # Check if expired
        if self.store._is_expired(hint):
            raise NudgeStoreError(
                ErrorCode.E_NOT_FOUND, f"Hint {component}/{key} has expired"
            )

        # Score and explain
        matches = Scorer.rank_hints([(component, key, hint)], context)
        if matches:
            match = matches[0]
            return {
                "hint": self._hint_to_dict(component, key, match.hint),
                "match_explain": {
                    "matched": match.match_explain.matched,
                    "score": match.match_explain.score,
                    "reasons": match.match_explain.reasons,
                },
            }

        # Hint didn't match context
        return {
            "hint": self._hint_to_dict(component, key, hint),
            "match_explain": {"matched": False, "score": 0.0, "reasons": []},
        }

    async def _handle_query(self, args: Dict) -> Dict:
        """Handle query tool call."""
        component = args.get("component")
        keys = args.get("keys", [])
        tags = args.get("tags", [])
        regex = args.get("regex")
        context_dict = args.get("context", {})
        limit = args.get("limit", 10)

        context = self._parse_context(context_dict)

        # Get all hints from the component (or all components)
        all_hints = self.store.get_all_hints(component)

        # Filter by keys
        if keys:
            all_hints = [(c, k, h) for c, k, h in all_hints if k in keys]

        # Filter by tags
        if tags:
            all_hints = [
                (c, k, h)
                for c, k, h in all_hints
                if h.meta and h.meta.tags and any(t in h.meta.tags for t in tags)
            ]

        # Filter by regex (on value)
        if regex:
            import re

            pattern = re.compile(regex)
            filtered = []
            for c, k, h in all_hints:
                text = SafetyGuard._extract_text(h.value)
                if pattern.search(text):
                    filtered.append((c, k, h))
            all_hints = filtered

        # Create mapping from hint id to (component, key) to preserve info after ranking
        hint_map = {id(h): (c, k) for c, k, h in all_hints}

        # Rank and filter expired
        matches = Scorer.rank_hints(all_hints, context)

        # Apply limit
        matches = matches[:limit]

        # Build response with component/key info from mapping
        hints_result = []
        for m in matches:
            comp, key = hint_map.get(id(m.hint), (None, None))
            if comp and key:
                hints_result.append({
                    "component": comp,
                    "key": key,
                    "hint": self._hint_to_dict(comp, key, m.hint),
                    "score": m.score,
                    "match_explain": {
                        "matched": m.match_explain.matched,
                        "score": m.match_explain.score,
                        "reasons": m.match_explain.reasons,
                    },
                })

        return {"hints": hints_result}

    async def _handle_delete_hint(self, args: Dict) -> Dict:
        """Handle delete_hint tool call."""
        component = args["component"]
        key = args["key"]

        deleted, previous = self.store.delete_hint(component, key)

        if not deleted:
            raise NudgeStoreError(
                ErrorCode.E_NOT_FOUND, f"Hint {component}/{key} not found"
            )

        return {
            "deleted": True,
            "previous": self._hint_to_dict(component, key, previous) if previous else None,
        }

    async def _handle_list_components(self, args: Dict) -> Dict:
        """Handle list_components tool call."""
        components = self.store.list_components()
        return {"components": components}

    async def _handle_bump(self, args: Dict) -> Dict:
        """Handle bump tool call."""
        component = args["component"]
        key = args["key"]
        delta = args.get("delta", 1)

        hint = self.store.bump(component, key, delta)

        if not hint:
            raise NudgeStoreError(
                ErrorCode.E_NOT_FOUND, f"Hint {component}/{key} not found"
            )

        return {"hint": self._hint_to_dict(component, key, hint)}

    async def _handle_export(self, args: Dict) -> Dict:
        """Handle export tool call."""
        format_type = args.get("format", "json")

        if format_type != "json":
            raise NudgeStoreError(
                ErrorCode.E_INVALID, f"Unsupported format: {format_type}"
            )

        payload = self.store.export_store()
        return {"payload": payload}

    async def _handle_import(self, args: Dict) -> Dict:
        """Handle import tool call."""
        payload = args["payload"]
        mode = args.get("mode", "merge")

        imported, skipped = self.store.import_store(payload, mode)

        return {"imported": imported, "skipped": skipped}

    def _parse_context(self, context_dict: Dict) -> NudgeContext:
        """Parse context dictionary into NudgeContext."""
        os_str = context_dict.get("os")
        os_enum = None
        if os_str:
            try:
                os_enum = OS(os_str)
            except ValueError:
                pass

        return NudgeContext(
            cwd=context_dict.get("cwd"),
            repo=context_dict.get("repo"),
            branch=context_dict.get("branch"),
            os=os_enum,
            env=context_dict.get("env"),
            files_open=context_dict.get("files_open"),
        )

    def _parse_meta(self, meta_dict: Dict) -> HintMeta:
        """Parse meta dictionary into HintMeta."""
        scope_dict = meta_dict.get("scope")
        scope = None
        if scope_dict:
            # Parse OS list
            os_list = scope_dict.get("os")
            if os_list:
                os_list = [OS(o) for o in os_list]

            scope = Scope(
                cwd_glob=scope_dict.get("cwd_glob"),
                repo=scope_dict.get("repo"),
                branch=scope_dict.get("branch"),
                os=os_list,
                env_required=scope_dict.get("env_required"),
                env_match=scope_dict.get("env_match"),
            )

        # Parse sensitivity
        sensitivity = meta_dict.get("sensitivity")
        if sensitivity:
            try:
                sensitivity = Sensitivity(sensitivity)
            except ValueError:
                sensitivity = None

        return HintMeta(
            reason=meta_dict.get("reason"),
            tags=meta_dict.get("tags"),
            priority=meta_dict.get("priority"),
            confidence=meta_dict.get("confidence"),
            ttl=meta_dict.get("ttl"),
            sensitivity=sensitivity,
            scope=scope,
            source=meta_dict.get("source"),
            added_by=meta_dict.get("added_by"),
        )

    def _hint_to_dict(self, component: str, key: str, hint: Hint) -> Dict:
        """Convert hint to dictionary for JSON response."""
        return self.store._hint_to_dict(hint)

    async def _handle_rpc_request(self, request: Dict) -> Dict:
        """
        Handle JSON-RPC request from IPC client.

        Args:
            request: JSON-RPC request

        Returns:
            JSON-RPC response
        """
        method = request.get('method')
        params = request.get('params', {})
        rpc_id = request.get('id')

        try:
            # Route to appropriate handler
            if method == "nudge.set_hint":
                result = await self._handle_set_hint(params)
            elif method == "nudge.get_hint":
                result = await self._handle_get_hint(params)
            elif method == "nudge.query":
                result = await self._handle_query(params)
            elif method == "nudge.delete_hint":
                result = await self._handle_delete_hint(params)
            elif method == "nudge.list_components":
                result = await self._handle_list_components(params)
            elif method == "nudge.bump":
                result = await self._handle_bump(params)
            elif method == "nudge.export":
                result = await self._handle_export(params)
            elif method == "nudge.import":
                result = await self._handle_import(params)
            else:
                return {
                    'jsonrpc': '2.0',
                    'error': {'code': -32601, 'message': f'Method not found: {method}'},
                    'id': rpc_id
                }

            return {
                'jsonrpc': '2.0',
                'result': result,
                'id': rpc_id
            }

        except NudgeStoreError as e:
            return {
                'jsonrpc': '2.0',
                'error': {
                    'code': e.code.value,
                    'message': e.message,
                    'data': e.data
                },
                'id': rpc_id
            }
        except Exception as e:
            logger.exception("Error handling RPC request")
            return {
                'jsonrpc': '2.0',
                'error': {
                    'code': -32603,
                    'message': str(e)
                },
                'id': rpc_id
            }

    async def run_as_proxy(self, primary_port: int):
        """
        Run as a proxy server that forwards MCP requests to PRIMARY via HTTP.

        Args:
            primary_port: Port of the PRIMARY server to forward to
        """
        from .client import NudgeClient

        # Create client to PRIMARY server
        client = NudgeClient(port=primary_port)

        # Create a new MCP server for proxy
        proxy_server = Server("nudge-proxy")

        # Register proxy tool handlers that forward to HTTP
        @proxy_server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available Nudge tools."""
            # Return same tool list as primary
            return [
                Tool(
                    name="nudge.set_hint",
                    description="Set or update a hint in the store",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key", "value"],
                        "properties": {
                            "component": {"type": "string", "minLength": 1},
                            "key": {"type": "string", "minLength": 1},
                            "value": {},
                            "meta": {"type": "object"},
                            "if_match_version": {"type": "integer", "minimum": 0},
                        },
                    },
                ),
                Tool(
                    name="nudge.get_hint",
                    description="Get the best matching hint for a component and key",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                            "context": {"type": "object"},
                        },
                    },
                ),
                Tool(
                    name="nudge.query",
                    description="Search for hints by component, keys, tags, or regex",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "component": {"type": "string"},
                            "keys": {"type": "array", "items": {"type": "string"}},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "regex": {"type": "string"},
                            "context": {"type": "object"},
                            "limit": {"type": "integer", "minimum": 1, "default": 10},
                        },
                    },
                ),
                Tool(
                    name="nudge.delete_hint",
                    description="Delete a hint from the store",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="nudge.list_components",
                    description="List all components with hint counts",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="nudge.bump",
                    description="Increase frecency counter after successful hint use",
                    inputSchema={
                        "type": "object",
                        "required": ["component", "key"],
                        "properties": {
                            "component": {"type": "string"},
                            "key": {"type": "string"},
                            "delta": {"type": "integer", "minimum": 1, "default": 1},
                        },
                    },
                ),
                Tool(
                    name="nudge.export",
                    description="Export the entire store or subset",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "format": {"type": "string", "enum": ["json"], "default": "json"}
                        },
                    },
                ),
                Tool(
                    name="nudge.import",
                    description="Import hints from a payload",
                    inputSchema={
                        "type": "object",
                        "required": ["payload"],
                        "properties": {
                            "payload": {"type": "object"},
                            "mode": {"type": "string", "enum": ["merge", "replace"], "default": "merge"},
                        },
                    },
                ),
            ]

        @proxy_server.call_tool()
        async def call_tool(name: str, arguments: Any) -> List[TextContent]:
            """Forward tool calls to PRIMARY via HTTP."""
            try:
                # Forward to HTTP backend based on method
                if name == "nudge.set_hint":
                    result = client.set_hint(
                        arguments["component"],
                        arguments["key"],
                        arguments["value"],
                        arguments.get("meta"),
                        arguments.get("if_match_version")
                    )
                elif name == "nudge.get_hint":
                    result = client.get_hint(
                        arguments["component"],
                        arguments["key"],
                        arguments.get("context")
                    )
                elif name == "nudge.query":
                    result = client.query(
                        arguments.get("component"),
                        arguments.get("keys"),
                        arguments.get("tags"),
                        arguments.get("regex"),
                        arguments.get("context"),
                        arguments.get("limit", 10)
                    )
                elif name == "nudge.delete_hint":
                    result = client.delete_hint(
                        arguments["component"],
                        arguments["key"]
                    )
                elif name == "nudge.list_components":
                    result = client.list_components()
                elif name == "nudge.bump":
                    result = client.bump(
                        arguments["component"],
                        arguments["key"],
                        arguments.get("delta", 1)
                    )
                elif name == "nudge.export":
                    result = client.export(arguments.get("format", "json"))
                elif name == "nudge.import":
                    result = client.import_hints(
                        arguments["payload"],
                        arguments.get("mode", "merge")
                    )
                else:
                    return [TextContent(type="text", text=json.dumps({"error": "Unknown tool"}))]

                return [TextContent(type="text", text=json.dumps(result))]

            except Exception as e:
                logger.exception("Error forwarding request to PRIMARY")
                error_response = {
                    "error": {
                        "code": "PROXY_ERROR",
                        "message": f"Proxy error: {str(e)}",
                        "data": {},
                    }
                }
                return [TextContent(type="text", text=json.dumps(error_response))]

        # Run proxy STDIO server
        logger.info(f"Starting PROXY mode, forwarding to PRIMARY on port {primary_port} (PID: {os.getpid()})")
        print(f"Nudge proxy started, forwarding to port {primary_port} (PID: {os.getpid()})")

        try:
            async with stdio_server() as (read_stream, write_stream):
                await proxy_server.run(
                    read_stream, write_stream, proxy_server.create_initialization_options()
                )
        except KeyboardInterrupt:
            logger.info("Proxy shutting down...")
        finally:
            logger.info("Proxy stopped")

    async def run(self, port: int = 8765):
        """
        Run the MCP server with both STDIO and HTTP channels (PRIMARY mode).

        Args:
            port: Requested port for HTTP server (will auto-increment if taken)
        """
        import asyncio

        # Create and start HTTP server
        self.http_server = NudgeHTTPServer(self._handle_rpc_request, port)
        actual_port = self.http_server.start()

        # Try to acquire lock with actual port
        try:
            self.lock.acquire(actual_port)
        except Exception as e:
            logger.error(str(e))
            print(f"Error: {e}")
            self.http_server.stop()
            return

        try:
            logger.info(f"PRIMARY server started on port {actual_port} (PID: {os.getpid()})")
            print(f"Nudge PRIMARY server started on port {actual_port} (PID: {os.getpid()})")

            # Run STDIO MCP server alongside HTTP
            async with stdio_server() as (read_stream, write_stream):
                # Create task for MCP STDIO server
                mcp_task = asyncio.create_task(
                    self.server.run(
                        read_stream, write_stream, self.server.create_initialization_options()
                    )
                )

                # Create task for HTTP server
                http_task = asyncio.create_task(self.http_server.serve_forever())

                # Wait for either task to complete (or both)
                await asyncio.gather(mcp_task, http_task, return_exceptions=True)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            # Cleanup
            self.http_server.stop()
            self.lock.release()
            logger.info("Server stopped")


async def main():
    """Main entry point for the MCP server."""
    server = NudgeServer()
    await server.run()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
