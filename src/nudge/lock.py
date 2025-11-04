"""Single-instance lock mechanism for Nudge server."""

import os
import signal
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime


def get_pid_file_path() -> Path:
    """Get path to PID file."""
    if os.name == 'nt':  # Windows
        base_dir = Path(os.environ.get('LOCALAPPDATA', '~')).expanduser()
        pid_dir = base_dir / 'nudge'
    else:  # Unix-like
        pid_dir = Path('/tmp/nudge')

    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir / 'server.pid'


class LockError(Exception):
    """Lock-related error."""
    pass


class ServerLock:
    """Manages single-instance lock for Nudge server."""

    def __init__(self):
        """Initialize server lock."""
        self.pid_file = get_pid_file_path()

    def check_running(self) -> Tuple[bool, Optional[int]]:
        """
        Check if another server is already running.

        Returns:
            Tuple of (is_running, port)
            - If is_running=True: Another server is running, port=its port
            - If is_running=False: No server running, port=None
        """
        # Check if PID file exists
        if self.pid_file.exists():
            existing_pid = self._read_pid()
            if existing_pid and self._is_process_running(existing_pid):
                # Another server is running - get its port
                existing_port = self.get_port()
                return (True, existing_port)

            # Stale PID file - clean up
            self._cleanup()

        return (False, None)

    def try_acquire(self, port: int) -> Tuple[bool, Optional[int]]:
        """
        Try to acquire the server lock.

        Args:
            port: Port number the server wants to run on

        Returns:
            Tuple of (acquired, existing_port)
            - If acquired=True: Lock was acquired, existing_port=None
            - If acquired=False: Lock already held, existing_port=port of running server
        """
        is_running, existing_port = self.check_running()
        if is_running:
            return (False, existing_port)

        # Write PID and port as JSON
        pid_data = {
            'pid': os.getpid(),
            'port': port,
            'started': datetime.utcnow().isoformat()
        }
        self.pid_file.write_text(json.dumps(pid_data))
        return (True, None)

    def acquire(self, port: int) -> None:
        """
        Acquire the server lock.

        Args:
            port: Port number the server is running on

        Raises:
            LockError: If another instance is already running
        """
        acquired, existing_port = self.try_acquire(port)
        if not acquired:
            existing_pid = self._read_pid()
            raise LockError(f"Nudge server already running (PID: {existing_pid})")

    def release(self) -> None:
        """Release the server lock."""
        self._cleanup()

    def _read_pid(self) -> Optional[int]:
        """Read PID from PID file (supports both JSON and legacy text format)."""
        try:
            content = self.pid_file.read_text().strip()

            # Try JSON format first
            try:
                data = json.loads(content)
                return data.get('pid')
            except json.JSONDecodeError:
                # Fall back to legacy text format (just PID number)
                return int(content)

        except (ValueError, FileNotFoundError):
            return None

    def get_port(self) -> Optional[int]:
        """
        Read port from PID file.

        Returns:
            Port number if found, None otherwise
        """
        try:
            content = self.pid_file.read_text().strip()
            data = json.loads(content)
            return data.get('port')
        except (json.JSONDecodeError, FileNotFoundError, ValueError):
            return None

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            # Send signal 0 - doesn't kill, just checks if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            # Windows might not support signal 0
            if os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, 0, pid)
                if handle == 0:
                    return False
                kernel32.CloseHandle(handle)
                return True
            return False

    def _cleanup(self) -> None:
        """Clean up lock files."""
        # Remove PID file
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass

    def get_running_pid(self) -> Optional[int]:
        """
        Get PID of running server, if any.

        Returns:
            PID if server is running, None otherwise
        """
        if not self.pid_file.exists():
            return None

        pid = self._read_pid()
        if pid and self._is_process_running(pid):
            return pid

        return None

    def stop_server(self) -> bool:
        """
        Stop the running server.

        Returns:
            True if server was stopped, False if no server was running
        """
        pid = self.get_running_pid()
        if not pid:
            return False

        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)

            # Wait a bit and check if it's still running
            import time
            time.sleep(0.5)

            if self._is_process_running(pid):
                # Still running, force kill
                os.kill(pid, signal.SIGKILL)

            # Clean up
            self._cleanup()
            return True

        except Exception as e:
            raise LockError(f"Failed to stop server: {e}")
