"""Tests for context matching."""

import pytest
from nudge.core.matching import Matcher
from nudge.core.models import Hint, HintMeta, Scope, NudgeContext, OS


def test_no_scope_always_eligible():
    """Test that hints without scope are always eligible."""
    hint = Hint(value="test")
    context = NudgeContext(cwd="/some/path")

    is_eligible, reasons = Matcher.is_eligible(hint, context)

    assert is_eligible is True
    assert "no scope restrictions" in reasons


def test_cwd_glob_matching():
    """Test cwd glob pattern matching."""
    scope = Scope(cwd_glob=["**/http-proxy*"])
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match
    context = NudgeContext(cwd="/work/http-proxy")
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match
    context = NudgeContext(cwd="/work/other-service")
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_branch_matching():
    """Test branch matching."""
    scope = Scope(branch=["main", "dev"])
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match
    context = NudgeContext(branch="dev")
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match
    context = NudgeContext(branch="feature")
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_os_matching():
    """Test OS matching."""
    scope = Scope(os=[OS.LINUX, OS.DARWIN])
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match
    context = NudgeContext(os=OS.LINUX)
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match
    context = NudgeContext(os=OS.WINDOWS)
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_env_required():
    """Test required environment variables."""
    scope = Scope(env_required=["API_KEY", "SECRET"])
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match (all required present)
    context = NudgeContext(env={"API_KEY": "xxx", "SECRET": "yyy", "OTHER": "zzz"})
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match (missing SECRET)
    context = NudgeContext(env={"API_KEY": "xxx"})
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_env_match():
    """Test environment variable value matching."""
    scope = Scope(env_match={"ENV": "prod", "REGION": ["us-east-1", "us-west-2"]})
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match
    context = NudgeContext(env={"ENV": "prod", "REGION": "us-east-1"})
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match (wrong ENV value)
    context = NudgeContext(env={"ENV": "dev", "REGION": "us-east-1"})
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False

    # Should not match (wrong REGION value)
    context = NudgeContext(env={"ENV": "prod", "REGION": "eu-west-1"})
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_combined_scope():
    """Test multiple scope conditions together."""
    scope = Scope(
        cwd_glob=["**/api*"],
        branch=["main", "dev"],
        os=[OS.LINUX],
    )
    hint = Hint(value="test", meta=HintMeta(scope=scope))

    # Should match (all conditions met)
    context = NudgeContext(
        cwd="/work/api-service",
        branch="dev",
        os=OS.LINUX,
    )
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is True

    # Should not match (wrong OS)
    context = NudgeContext(
        cwd="/work/api-service",
        branch="dev",
        os=OS.WINDOWS,
    )
    is_eligible, reasons = Matcher.is_eligible(hint, context)
    assert is_eligible is False


def test_scope_specificity_counting():
    """Test scope specificity calculation."""
    # No scope
    assert Matcher.count_scope_specificity(None) == 0

    # Empty scope
    scope = Scope()
    assert Matcher.count_scope_specificity(scope) == 0

    # One field
    scope = Scope(os=[OS.LINUX])
    assert Matcher.count_scope_specificity(scope) == 1

    # Multiple fields
    scope = Scope(
        cwd_glob=["**"],
        branch=["main"],
        os=[OS.LINUX],
        env_required=["KEY1", "KEY2"],
    )
    # cwd_glob (1) + branch (1) + os (1) + env_required (2) = 5
    assert Matcher.count_scope_specificity(scope) == 5
