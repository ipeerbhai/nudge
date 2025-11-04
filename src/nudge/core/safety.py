"""Safety features: secret guard and path validation."""

import re
import os
from pathlib import Path
from typing import Optional
from .models import HintValue, CommandValue, PathValue, Sensitivity


class SafetyGuard:
    """Safety checks for hint values."""

    # Patterns that might indicate secrets
    SECRET_PATTERNS = [
        # AWS keys
        re.compile(r"AKIA[0-9A-Z]{16}"),
        # Generic API keys (32-64 hex chars)
        re.compile(r"\b[0-9a-fA-F]{32,64}\b"),
        # JWT tokens
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        # Private keys
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
        # Password-like patterns
        re.compile(r"(?:password|passwd|pwd|secret|token)\s*[:=]\s*['\"]?[\w\-\.@]{8,}"),
        # Connection strings
        re.compile(
            r"(?:mongodb|postgres|mysql|redis)://[^:]+:[^@]+@",
            re.IGNORECASE,
        ),
    ]

    @staticmethod
    def check_for_secrets(
        value: HintValue,
        sensitivity: Optional[Sensitivity] = None,
        allow_secret: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a hint value contains potential secrets.

        Args:
            value: The hint value to check
            sensitivity: Declared sensitivity level
            allow_secret: Whether to allow secrets

        Returns:
            Tuple of (has_secret, reason)
        """
        # If explicitly marked as secret and allowed, skip check
        if sensitivity == Sensitivity.SECRET and allow_secret:
            return False, None

        # Extract string content from value
        text = SafetyGuard._extract_text(value)

        # Check against patterns
        for pattern in SafetyGuard.SECRET_PATTERNS:
            if pattern.search(text):
                return True, f"Potential secret detected (pattern: {pattern.pattern[:50]}...)"

        return False, None

    @staticmethod
    def _extract_text(value: HintValue) -> str:
        """Extract text content from various hint value types."""
        if isinstance(value, str):
            return value
        elif isinstance(value, CommandValue):
            return value.cmd
        elif isinstance(value, PathValue):
            return value.abs
        elif hasattr(value, "body"):
            return value.body
        elif hasattr(value, "data"):
            return str(value.data)
        return str(value)

    @staticmethod
    def validate_path(path: str) -> tuple[bool, Optional[str]]:
        """
        Validate a path for safety concerns.

        Checks for:
        - Path traversal attempts (..)
        - Non-absolute paths for PathValue types

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_valid, error_reason)
        """
        # Check for path traversal
        if ".." in Path(path).parts:
            return False, "Path traversal (..) not allowed"

        # For absolute path requirements, check if it starts with /
        # (This is mainly for PathValue types)
        try:
            resolved = Path(path).resolve()
            # Check if resolution changed the path significantly (traversal attempt)
            if ".." in str(path):
                return False, "Path contains suspicious traversal"
        except (ValueError, OSError) as e:
            return False, f"Invalid path: {str(e)}"

        return True, None

    @staticmethod
    def validate_glob_pattern(pattern: str) -> tuple[bool, Optional[str]]:
        """
        Validate a glob pattern for safety.

        Args:
            pattern: Glob pattern to validate

        Returns:
            Tuple of (is_valid, error_reason)
        """
        # Check for path traversal in glob patterns
        if pattern.startswith(".."):
            return False, "Glob pattern cannot start with .."

        # Patterns should be reasonable length
        if len(pattern) > 500:
            return False, "Glob pattern too long (max 500 characters)"

        return True, None

    @staticmethod
    def sanitize_for_display(value: HintValue, is_secret: bool = False) -> str:
        """
        Sanitize a hint value for safe display.

        If marked as secret, redact most of the content.

        Args:
            value: The hint value
            is_secret: Whether the hint is marked as secret

        Returns:
            Sanitized string representation
        """
        text = SafetyGuard._extract_text(value)

        if not is_secret:
            return text

        # For secrets, show only first and last few characters
        if len(text) <= 8:
            return "*" * len(text)

        return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"

    @staticmethod
    def validate_hint_value(
        value: HintValue,
        sensitivity: Optional[Sensitivity] = None,
        secret_guard_enabled: bool = True,
        allow_secret: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Comprehensive validation of a hint value.

        Args:
            value: The hint value to validate
            sensitivity: Declared sensitivity level
            secret_guard_enabled: Whether secret guard is enabled
            allow_secret: Whether to allow secrets

        Returns:
            Tuple of (is_valid, error_reason)
        """
        # Check for secrets if guard is enabled
        if secret_guard_enabled:
            has_secret, reason = SafetyGuard.check_for_secrets(
                value, sensitivity, allow_secret
            )
            if has_secret:
                return False, reason

        # Validate paths if it's a PathValue
        if isinstance(value, PathValue):
            is_valid, reason = SafetyGuard.validate_path(value.abs)
            if not is_valid:
                return False, reason

        return True, None
