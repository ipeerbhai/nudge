"""RPC client for Nudge CLI commands."""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from pathlib import Path


class NudgeClientError(Exception):
    """Client communication error."""
    pass


class NudgeClient:
    """High-level client for Nudge RPC calls."""

    DEFAULT_PORT = 8765

    def __init__(self, port: Optional[int] = None, timeout: float = 5.0):
        """
        Initialize Nudge client.

        Args:
            port: Port to connect to (None = auto-discover)
            timeout: Connection timeout in seconds
        """
        self.timeout = timeout
        self.port = port if port is not None else self._discover_port()

    def _discover_port(self) -> int:
        """
        Discover server port.

        Priority:
        1. Read from PID file
        2. Default port 8765

        Returns:
            Port number to use
        """
        # Try to read from PID file
        from .lock import get_pid_file_path

        pid_file = get_pid_file_path()
        if pid_file.exists():
            try:
                data = json.loads(pid_file.read_text())
                port = data.get('port')
                if port:
                    return port
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        # Fall back to default
        return self.DEFAULT_PORT

    def _call_rpc(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Make an RPC call to the server.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            Method result

        Raises:
            NudgeClientError: On communication or RPC errors
        """
        url = f"http://localhost:{self.port}/"

        request_data = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
            'id': 1
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(request_data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode('utf-8'))

                if 'error' in response_data:
                    error = response_data['error']
                    raise NudgeClientError(f"RPC error: {error.get('message', 'Unknown error')}")

                return response_data.get('result')

        except urllib.error.URLError as e:
            raise NudgeClientError(f"Server not found on port {self.port}")
        except urllib.error.HTTPError as e:
            raise NudgeClientError(f"HTTP error {e.code}: {e.reason}")
        except json.JSONDecodeError:
            raise NudgeClientError("Invalid response from server")
        except Exception as e:
            raise NudgeClientError(f"Communication error: {str(e)}")

    def set_hint(
        self,
        component: str,
        key: str,
        value: Any,
        meta: Optional[Dict] = None,
        if_match_version: Optional[int] = None
    ) -> Dict:
        """Set or update a hint."""
        params = {
            'component': component,
            'key': key,
            'value': value,
        }
        if meta:
            params['meta'] = meta
        if if_match_version is not None:
            params['if_match_version'] = if_match_version

        return self._call_rpc('nudge_set_hint', params)

    def get_hint(
        self,
        component: str,
        key: str,
        context: Optional[Dict] = None
    ) -> Dict:
        """Get a hint by component and key."""
        params = {
            'component': component,
            'key': key,
        }
        if context:
            params['context'] = context

        return self._call_rpc('nudge_get_hint', params)

    def query(
        self,
        component: Optional[str] = None,
        keys: Optional[list] = None,
        tags: Optional[list] = None,
        regex: Optional[str] = None,
        context: Optional[Dict] = None,
        limit: int = 10
    ) -> Dict:
        """Query hints."""
        params = {'limit': limit}
        if component:
            params['component'] = component
        if keys:
            params['keys'] = keys
        if tags:
            params['tags'] = tags
        if regex:
            params['regex'] = regex
        if context:
            params['context'] = context

        return self._call_rpc('nudge_query', params)

    def delete_hint(self, component: str, key: str) -> Dict:
        """Delete a hint."""
        params = {
            'component': component,
            'key': key,
        }
        return self._call_rpc('nudge_delete_hint', params)

    def list_components(self) -> Dict:
        """List all components."""
        return self._call_rpc('nudge_list_components', {})

    def bump(self, component: str, key: str, delta: int = 1) -> Dict:
        """Increase frecency counter."""
        params = {
            'component': component,
            'key': key,
            'delta': delta,
        }
        return self._call_rpc('nudge_bump', params)

    def export(self, format: str = 'json') -> Dict:
        """Export the store."""
        params = {'format': format}
        return self._call_rpc('nudge_export', params)

    def import_hints(self, payload: Dict, mode: str = 'merge') -> Dict:
        """Import hints."""
        params = {
            'payload': payload,
            'mode': mode,
        }
        return self._call_rpc('nudge_import', params)
