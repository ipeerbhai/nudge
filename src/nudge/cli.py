"""CLI interface for Nudge."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .client import NudgeClient, NudgeClientError
from .lock import ServerLock
from .core.models import OS
from .utils.context import auto_detect_context


def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Nudge - Session-scoped hint cache for coding agents",
        prog="nudge",
    )
    parser.add_argument("--version", action="version", version="nudge 0.1.0")
    parser.add_argument(
        "--json", action="store_true", help="Output in JSON format (for scripting)"
    )
    parser.add_argument(
        "-p", "--port", type=int, help="HTTP server port (default: auto-discover)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start MCP server")
    serve_parser.add_argument(
        "--port", type=int, default=8765, help="HTTP server port (default: 8765)"
    )

    # status command
    status_parser = subparsers.add_parser("status", help="Check server status")

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop running server")

    # set command
    set_parser = subparsers.add_parser("set", help="Set or update a hint")
    set_parser.add_argument("component", help="Component name")
    set_parser.add_argument("key", help="Hint key")
    set_parser.add_argument("value", help="Hint value")
    set_parser.add_argument("--tags", help="Comma-separated tags")
    set_parser.add_argument("--priority", type=int, help="Priority (1-10)")
    set_parser.add_argument("--confidence", type=float, help="Confidence (0.0-1.0)")
    set_parser.add_argument("--ttl", help="TTL ('session' or ISO-8601 duration)")
    set_parser.add_argument("--scope-cwd-glob", help="Cwd glob pattern")
    set_parser.add_argument("--scope-branch", help="Comma-separated branches")
    set_parser.add_argument("--scope-os", help="Comma-separated OS (linux,darwin,windows)")
    set_parser.add_argument("--allow-secret", action="store_true", help="Allow secret values")

    # get command
    get_parser = subparsers.add_parser("get", help="Get a hint")
    get_parser.add_argument("component", help="Component name")
    get_parser.add_argument("key", help="Hint key")
    get_parser.add_argument("--cwd", help="Override current working directory")
    get_parser.add_argument("--branch", help="Override git branch")
    get_parser.add_argument("--os", help="Override OS")

    # query command
    query_parser = subparsers.add_parser("query", help="Query hints")
    query_parser.add_argument("--component", help="Filter by component")
    query_parser.add_argument("--tags", help="Comma-separated tags to filter")
    query_parser.add_argument("--limit", type=int, default=10, help="Max results")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a hint")
    delete_parser.add_argument("component", help="Component name")
    delete_parser.add_argument("key", help="Hint key")

    # bump command
    bump_parser = subparsers.add_parser("bump", help="Increase frecency counter")
    bump_parser.add_argument("component", help="Component name")
    bump_parser.add_argument("key", help="Hint key")
    bump_parser.add_argument("--delta", type=int, default=1, help="Increment amount")

    # list-components command (with 'ls' alias)
    list_parser = subparsers.add_parser("list-components", aliases=["ls"], help="List all components or keys in a component")
    list_parser.add_argument("component", nargs="?", help="Optional: component name to list keys for")

    # export command
    export_parser = subparsers.add_parser("export", help="Export store to JSON")
    export_parser.add_argument("--format", default="json", help="Export format")

    # import command
    import_parser = subparsers.add_parser("import", help="Import hints from JSON file")
    import_parser.add_argument("file", help="JSON file to import")
    import_parser.add_argument("--mode", default="merge", choices=["merge", "replace"])

    # blob-upload command
    blob_upload_parser = subparsers.add_parser("blob-upload", help="Upload a file as a blob")
    blob_upload_parser.add_argument("file", help="File to upload")
    blob_upload_parser.add_argument("--content-type", help="MIME type (auto-detected if not provided)")
    blob_upload_parser.add_argument("--filename", help="Override filename")

    # blob-download command
    blob_download_parser = subparsers.add_parser("blob-download", help="Download a blob")
    blob_download_parser.add_argument("blob_id", help="Blob ID to download")
    blob_download_parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    # blob-list command
    blob_list_parser = subparsers.add_parser("blob-list", help="List all blobs")

    # blob-delete command
    blob_delete_parser = subparsers.add_parser("blob-delete", help="Delete a blob")
    blob_delete_parser.add_argument("blob_id", help="Blob ID to delete")

    # blob-info command
    blob_info_parser = subparsers.add_parser("blob-info", help="Get blob metadata")
    blob_info_parser.add_argument("blob_id", help="Blob ID to get info for")

    return parser


def cmd_serve(args):
    """Start the MCP server (PRIMARY or PROXY mode)."""
    import asyncio
    from .server import NudgeServer
    from .lock import ServerLock

    # Check if another server is already running
    lock = ServerLock()
    is_running, existing_port = lock.check_running()

    server = NudgeServer()

    if is_running and existing_port:
        # Another server is running - run as PROXY
        asyncio.run(server.run_as_proxy(primary_port=existing_port))
    else:
        # No server running - run as PRIMARY
        # (run() will handle lock acquisition)
        asyncio.run(server.run(port=args.port))


def cmd_status():
    """Check server status."""
    lock = ServerLock()
    pid = lock.get_running_pid()

    if pid:
        return {"running": True, "pid": pid}
    else:
        return {"running": False}


def cmd_stop():
    """Stop the running server."""
    lock = ServerLock()
    pid = lock.get_running_pid()

    if not pid:
        return {"stopped": False, "message": "No server running"}

    success = lock.stop_server()
    if success:
        return {"stopped": True, "pid": pid}
    else:
        return {"stopped": False, "message": "Failed to stop server"}


def cmd_set(client: NudgeClient, args) -> dict:
    """Handle set command."""
    # Build meta dict
    meta = {}

    if args.tags:
        meta['tags'] = [t.strip() for t in args.tags.split(",")]

    if args.priority is not None:
        meta['priority'] = args.priority

    if args.confidence is not None:
        meta['confidence'] = args.confidence

    if args.ttl:
        meta['ttl'] = args.ttl

    # Build scope
    scope = {}

    if args.scope_cwd_glob:
        scope['cwd_glob'] = [args.scope_cwd_glob]

    if args.scope_branch:
        scope['branch'] = [b.strip() for b in args.scope_branch.split(",")]

    if args.scope_os:
        scope['os'] = [o.strip() for o in args.scope_os.split(",")]

    if scope:
        meta['scope'] = scope

    # Set hint via RPC
    result = client.set_hint(args.component, args.key, args.value, meta if meta else None)

    hint = result.get('hint', {})
    return {
        "success": True,
        "component": args.component,
        "key": args.key,
        "version": hint.get('version', 1),
    }


def cmd_get(client: NudgeClient, args) -> dict:
    """Handle get command."""
    # Build context
    context_obj = auto_detect_context()

    # Override with args
    context = {
        'cwd': args.cwd if args.cwd else context_obj.cwd,
        'branch': args.branch if args.branch else context_obj.branch,
        'os': args.os if args.os else (context_obj.os.value if context_obj.os else None),
        'repo': context_obj.repo,
        'env': context_obj.env,
    }

    # Get hint via RPC
    result = client.get_hint(args.component, args.key, context)

    # Extract value and match info
    hint = result.get('hint', {})
    match_explain = result.get('match_explain', {})

    value = hint.get('value', '')
    if isinstance(value, dict):
        # Extract from structured value
        if 'cmd' in value:
            value = value['cmd']
        elif 'abs' in value:
            value = value['abs']
        elif 'body' in value:
            value = value['body']

    return {
        "value": value,
        "match": {
            "score": match_explain.get('score', 0.0),
            "reasons": match_explain.get('reasons', []),
        },
    }


def cmd_query(client: NudgeClient, args) -> dict:
    """Handle query command."""
    context_obj = auto_detect_context()
    context = {
        'cwd': context_obj.cwd,
        'branch': context_obj.branch,
        'os': context_obj.os.value if context_obj.os else None,
        'repo': context_obj.repo,
    }

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    # Query via RPC
    result = client.query(
        component=args.component,
        tags=tags,
        context=context,
        limit=args.limit
    )

    hints = result.get('hints', [])

    return {
        "count": len(hints),
        "hints": [
            {
                "component": h.get('component', ''),
                "key": h.get('key', ''),
                "score": h.get('score', 0.0),
                "value": h.get('hint', {}).get('value', ''),
                "tags": h.get('hint', {}).get('meta', {}).get('tags', []),
            }
            for h in hints
        ],
    }


def cmd_delete(client: NudgeClient, args) -> dict:
    """Handle delete command."""
    result = client.delete_hint(args.component, args.key)
    return {"deleted": result.get('deleted', False), "component": args.component, "key": args.key}


def cmd_bump(client: NudgeClient, args) -> dict:
    """Handle bump command."""
    result = client.bump(args.component, args.key, args.delta)
    hint = result.get('hint', {})

    return {
        "component": args.component,
        "key": args.key,
        "use_count": hint.get('use_count', 0),
        "last_used_at": hint.get('last_used_at'),
    }


def cmd_list_components(client: NudgeClient, args) -> dict:
    """Handle list-components command."""
    # If component specified, list keys in that component
    if args.component:
        context_obj = auto_detect_context()
        context = {
            'cwd': context_obj.cwd,
            'branch': context_obj.branch,
            'os': context_obj.os.value if context_obj.os else None,
            'repo': context_obj.repo,
        }

        # Query all hints for this component
        result = client.query(
            component=args.component,
            context=context,
            limit=1000
        )

        hints = result.get('hints', [])
        # Filter to only include hints from the requested component
        # (server may return all hints if component doesn't exist)
        hints = [h for h in hints if h.get('component') == args.component]
        keys = [h.get('key', '') for h in hints]

        return {
            "component": args.component,
            "keys": keys,
            "count": len(keys)
        }

    # Otherwise, list all components
    result = client.list_components()
    return {"components": result.get('components', [])}


def cmd_export(client: NudgeClient, args) -> dict:
    """Handle export command."""
    result = client.export(args.format)
    return result.get('payload', {})


def cmd_import(client: NudgeClient, args) -> dict:
    """Handle import command."""
    with open(args.file, "r") as f:
        payload = json.load(f)

    result = client.import_hints(payload, args.mode)
    return {"imported": result.get('imported', 0), "skipped": result.get('skipped', 0)}


def cmd_blob_upload(client: NudgeClient, args) -> dict:
    """Handle blob-upload command."""
    file_path = Path(args.file)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {args.file}")

    with open(file_path, "rb") as f:
        data = f.read()

    filename = args.filename if args.filename else file_path.name
    content_type = getattr(args, 'content_type', None)

    result = client.blob_upload(data, filename, content_type)

    return {
        "blob_id": result.get("blob_id"),
        "filename": result.get("filename"),
        "size": result.get("size"),
        "content_type": result.get("content_type"),
        "checksum": result.get("checksum"),
    }


def cmd_blob_download(client: NudgeClient, args) -> dict:
    """Handle blob-download command."""
    data, metadata = client.blob_download(args.blob_id)

    if args.output:
        with open(args.output, "wb") as f:
            f.write(data)
        return {
            "downloaded": True,
            "blob_id": args.blob_id,
            "output": args.output,
            "size": len(data),
        }
    else:
        # Write to stdout in binary mode
        sys.stdout.buffer.write(data)
        return None  # No pretty output for binary


def cmd_blob_list(client: NudgeClient, args) -> dict:
    """Handle blob-list command."""
    result = client.blob_list()
    return {"blobs": result.get("blobs", [])}


def cmd_blob_delete(client: NudgeClient, args) -> dict:
    """Handle blob-delete command."""
    client.blob_delete(args.blob_id)
    return {"deleted": True, "blob_id": args.blob_id}


def cmd_blob_info(client: NudgeClient, args) -> dict:
    """Handle blob-info command."""
    result = client.blob_info(args.blob_id)
    return {
        "blob_id": result.get("blob_id"),
        "filename": result.get("filename"),
        "content_type": result.get("content_type"),
        "size": result.get("size"),
        "created_at": result.get("created_at"),
        "checksum": result.get("checksum"),
    }


def pretty_print(result: dict, json_mode: bool):
    """Pretty print result."""
    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        # Simple pretty printing
        if "value" in result:
            print(f"value: {result['value']}")
            if "match" in result:
                match = result["match"]
                print(f"match:")
                print(f"  score: {match['score']}")
                print(f"  reasons:")
                for reason in match["reasons"]:
                    print(f"    - {reason}")
        elif "components" in result:
            components = result["components"]
            # Export format: components is a dict with schema_version
            if "schema_version" in result:
                print(json.dumps(result, indent=2))
            # List-components format: components is a list
            elif isinstance(components, list):
                print("Components:")
                for comp in components:
                    print(f"  {comp['name']}: {comp['hint_count']} hint(s)")
            else:
                # Fallback for other dict formats
                print(json.dumps(result, indent=2))
        elif "keys" in result:
            print(f"Keys in '{result['component']}':")
            if result['keys']:
                for key in result['keys']:
                    print(f"  {key}")
            else:
                print("  (no keys found)")
        elif "hints" in result:
            print(f"Found {result['count']} hint(s):")
            for hint in result["hints"]:
                print(f"  {hint['component']}/{hint['key']}")
                print(f"  score: {hint['score']}")
                print(f"  value: {hint['value']}")
                if hint['tags']:
                    print(f"  tags: {', '.join(hint['tags'])}")
                print()
        elif "success" in result:
            print(f"✓ Set {result['component']}/{result['key']} (v{result['version']})")
        elif "deleted" in result and "blob_id" in result:
            print(f"✓ Deleted blob {result['blob_id']}")
        elif "deleted" in result:
            print(f"✓ Deleted {result['component']}/{result['key']}")
        elif "blobs" in result:
            blobs = result["blobs"]
            if not blobs:
                print("No blobs stored")
            else:
                print(f"Blobs ({len(blobs)}):")
                for blob in blobs:
                    print(f"  {blob['blob_id']}")
                    print(f"    filename: {blob.get('filename', 'N/A')}")
                    print(f"    size: {blob.get('size', 0)} bytes")
                    print(f"    type: {blob.get('content_type', 'N/A')}")
                    print()
        elif "blob_id" in result and "checksum" in result and "size" in result:
            # blob-upload or blob-info result
            if "downloaded" in result:
                print(f"✓ Downloaded blob {result['blob_id']} to {result['output']}")
                print(f"  size: {result['size']} bytes")
            else:
                print(f"Blob: {result['blob_id']}")
                print(f"  filename: {result.get('filename', 'N/A')}")
                print(f"  size: {result.get('size', 0)} bytes")
                print(f"  type: {result.get('content_type', 'N/A')}")
                if 'created_at' in result:
                    print(f"  created: {result['created_at']}")
                print(f"  checksum: {result.get('checksum', 'N/A')}")
        elif "use_count" in result:
            print(f"↑ Bumped {result['component']}/{result['key']}")
            print(f"  use_count: {result['use_count']}")
            print(f"  last_used_at: {result['last_used_at']}")
        elif "imported" in result:
            print(f"✓ Imported {result['imported']} hint(s), skipped {result['skipped']}")
        elif "running" in result:
            if result['running']:
                print(f"Nudge server is running (PID: {result['pid']})")
            else:
                print("Nudge server is not running")
        elif "stopped" in result:
            if result['stopped']:
                print(f"✓ Server stopped (PID: {result['pid']})")
            else:
                print(f"✗ {result.get('message', 'Failed to stop server')}")
        else:
            print(json.dumps(result, indent=2))


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Special cases that don't need client
    if args.command == "serve":
        cmd_serve(args)
        return
    elif args.command == "status":
        result = cmd_status()
        pretty_print(result, args.json)
        return
    elif args.command == "stop":
        result = cmd_stop()
        pretty_print(result, args.json)
        return

    # For other commands, create a client
    client = NudgeClient(port=args.port)

    try:
        if args.command == "set":
            result = cmd_set(client, args)
        elif args.command == "get":
            result = cmd_get(client, args)
        elif args.command == "query":
            result = cmd_query(client, args)
        elif args.command == "delete":
            result = cmd_delete(client, args)
        elif args.command == "bump":
            result = cmd_bump(client, args)
        elif args.command in ("list-components", "ls"):
            result = cmd_list_components(client, args)
        elif args.command == "export":
            result = cmd_export(client, args)
        elif args.command == "import":
            result = cmd_import(client, args)
        elif args.command == "blob-upload":
            result = cmd_blob_upload(client, args)
        elif args.command == "blob-download":
            result = cmd_blob_download(client, args)
        elif args.command == "blob-list":
            result = cmd_blob_list(client, args)
        elif args.command == "blob-delete":
            result = cmd_blob_delete(client, args)
        elif args.command == "blob-info":
            result = cmd_blob_info(client, args)
        else:
            parser.print_help()
            sys.exit(1)

        if result is not None:  # blob-download to stdout returns None
            pretty_print(result, args.json)

    except NudgeClientError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
