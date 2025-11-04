"""Tests for the core store."""

import pytest
from nudge.core.store import Store, NudgeStoreError
from nudge.core.models import HintMeta, ErrorCode


def test_set_and_get_hint():
    """Test basic set and get operations."""
    store = Store()

    # Set a hint
    hint = store.set_hint("test-component", "test-key", "test value")

    assert hint.value == "test value"
    assert hint.version == 1

    # Get the hint
    retrieved = store.get_hint("test-component", "test-key")

    assert retrieved is not None
    assert retrieved.value == "test value"
    assert retrieved.version == 1


def test_update_hint_increments_version():
    """Test that updating a hint increments version."""
    store = Store()

    # Set initial hint
    store.set_hint("comp", "key", "value1")

    # Update hint
    hint = store.set_hint("comp", "key", "value2")

    assert hint.value == "value2"
    assert hint.version == 2


def test_version_conflict():
    """Test optimistic concurrency with version conflicts."""
    store = Store()

    store.set_hint("comp", "key", "value1")

    # Try to update with wrong version
    with pytest.raises(NudgeStoreError) as exc_info:
        store.set_hint("comp", "key", "value2", if_match_version=5)

    assert exc_info.value.code == ErrorCode.E_CONFLICT


def test_delete_hint():
    """Test deleting a hint."""
    store = Store()

    store.set_hint("comp", "key", "value")

    deleted, previous = store.delete_hint("comp", "key")

    assert deleted is True
    assert previous.value == "value"

    # Verify it's gone
    assert store.get_hint("comp", "key") is None


def test_bump():
    """Test bumping use count."""
    store = Store()

    store.set_hint("comp", "key", "value")

    hint = store.bump("comp", "key", 1)

    assert hint.use_count == 1
    assert hint.last_used_at is not None

    # Bump again
    hint = store.bump("comp", "key", 2)

    assert hint.use_count == 3


def test_list_components():
    """Test listing components."""
    store = Store()

    store.set_hint("comp1", "key1", "value1")
    store.set_hint("comp1", "key2", "value2")
    store.set_hint("comp2", "key1", "value1")

    components = store.list_components()

    assert len(components) == 2
    assert any(c["name"] == "comp1" and c["hint_count"] == 2 for c in components)
    assert any(c["name"] == "comp2" and c["hint_count"] == 1 for c in components)


def test_quota_enforcement():
    """Test that quota limits are enforced."""
    store = Store(max_components=2, max_hints_per_component=2, max_total_hints=5)

    # Fill up the store
    store.set_hint("comp1", "key1", "value1")
    store.set_hint("comp1", "key2", "value2")
    store.set_hint("comp2", "key1", "value1")

    # Try to add third hint to comp1 (exceeds per-component limit)
    with pytest.raises(NudgeStoreError) as exc_info:
        store.set_hint("comp1", "key3", "value3")

    assert exc_info.value.code == ErrorCode.E_QUOTA
