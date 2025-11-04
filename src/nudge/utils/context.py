"""Context auto-detection utilities."""

import os
import platform
import subprocess
from typing import Optional
from ..core.models import OS, NudgeContext


def detect_os() -> Optional[OS]:
    """
    Detect the current operating system.

    Returns:
        OS enum value, or None if unknown
    """
    system = platform.system().lower()

    if system == "linux":
        return OS.LINUX
    elif system == "darwin":
        return OS.DARWIN
    elif system == "windows":
        return OS.WINDOWS

    return None


def detect_repo() -> Optional[str]:
    """
    Detect the current git repository.

    Returns:
        Repo URL or file path, or None if not in a repo
    """
    try:
        # Try to get remote URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            return result.stdout.strip()

        # Fall back to local repo path
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            repo_path = result.stdout.strip()
            return f"file://{repo_path}"

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def detect_branch() -> Optional[str]:
    """
    Detect the current git branch.

    Returns:
        Branch name, or None if not in a repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            return result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def detect_cwd() -> str:
    """
    Get the current working directory.

    Returns:
        Current working directory path
    """
    return os.getcwd()


def auto_detect_context() -> NudgeContext:
    """
    Auto-detect context from the current environment.

    Returns:
        NudgeContext with detected values
    """
    return NudgeContext(
        cwd=detect_cwd(),
        repo=detect_repo(),
        branch=detect_branch(),
        os=detect_os(),
        env=dict(os.environ),
    )
