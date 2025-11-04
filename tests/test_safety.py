"""Tests for safety features."""

import pytest
from nudge.core.safety import SafetyGuard
from nudge.core.models import PathValue


def test_detect_aws_key():
    """Test detection of AWS access keys."""
    value = "AKIAIOSFODNN7EXAMPLE"

    has_secret, reason = SafetyGuard.check_for_secrets(value)

    assert has_secret is True
    assert reason is not None


def test_detect_jwt():
    """Test detection of JWT tokens."""
    value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

    has_secret, reason = SafetyGuard.check_for_secrets(value)

    assert has_secret is True


def test_detect_hex_key():
    """Test detection of long hex strings (potential keys)."""
    value = "a" * 32  # 32 character hex string

    has_secret, reason = SafetyGuard.check_for_secrets(value)

    assert has_secret is True


def test_normal_text_not_secret():
    """Test that normal text is not flagged as secret."""
    value = "docker compose build router"

    has_secret, reason = SafetyGuard.check_for_secrets(value)

    assert has_secret is False


def test_validate_path_traversal():
    """Test detection of path traversal attempts."""
    # Path with .. should be rejected
    is_valid, reason = SafetyGuard.validate_path("/some/path/../../../etc/passwd")

    assert is_valid is False
    assert "traversal" in reason.lower()


def test_validate_normal_path():
    """Test that normal paths are accepted."""
    is_valid, reason = SafetyGuard.validate_path("/home/user/project")

    assert is_valid is True
    assert reason is None


def test_validate_glob_pattern():
    """Test glob pattern validation."""
    # Normal pattern should pass
    is_valid, reason = SafetyGuard.validate_glob_pattern("**/src/*.js")
    assert is_valid is True

    # Pattern starting with .. should fail
    is_valid, reason = SafetyGuard.validate_glob_pattern("../**/src")
    assert is_valid is False


def test_sanitize_secret():
    """Test sanitization of secret values."""
    value = "supersecretpassword123"

    sanitized = SafetyGuard.sanitize_for_display(value, is_secret=True)

    # Shows first 4 and last 4 chars with asterisks in between
    assert "supe" in sanitized
    assert "d123" in sanitized
    assert "*" in sanitized
    assert len(sanitized) == len(value)


def test_sanitize_normal():
    """Test that normal values are not sanitized."""
    value = "normal value"

    sanitized = SafetyGuard.sanitize_for_display(value, is_secret=False)

    assert sanitized == value


def test_validate_hint_value():
    """Test comprehensive hint value validation."""
    # Normal value should pass
    is_valid, reason = SafetyGuard.validate_hint_value("docker build", None, True, False)
    assert is_valid is True

    # Value with secret should fail if guard enabled
    is_valid, reason = SafetyGuard.validate_hint_value(
        "AKIAIOSFODNN7EXAMPLE", None, True, False
    )
    assert is_valid is False

    # Same value should pass if guard disabled
    is_valid, reason = SafetyGuard.validate_hint_value(
        "AKIAIOSFODNN7EXAMPLE", None, False, False
    )
    assert is_valid is True
