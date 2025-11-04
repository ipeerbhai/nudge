"""Core in-memory hint store implementation."""

import uuid
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from .models import (
    Hint,
    HintMeta,
    HintValue,
    ComponentHints,
    NudgeStore,
    NudgeContext,
    ErrorCode,
)


class NudgeStoreError(Exception):
    """Base exception for store errors."""

    def __init__(self, code: ErrorCode, message: str, data: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)


class Store:
    """In-memory hint store with CRUD operations."""

    def __init__(
        self,
        max_components: int = 500,
        max_hints_per_component: int = 200,
        max_total_hints: int = 5000,
    ):
        """Initialize the store with size limits."""
        self.max_components = max_components
        self.max_hints_per_component = max_hints_per_component
        self.max_total_hints = max_total_hints

        self.store = NudgeStore(
            session_id=str(uuid.uuid4()),
            created_at=datetime.utcnow().isoformat(),
        )

    def set_hint(
        self,
        component: str,
        key: str,
        value: HintValue,
        meta: Optional[HintMeta] = None,
        if_match_version: Optional[int] = None,
    ) -> Hint:
        """
        Set or update a hint.

        Args:
            component: Component name
            key: Hint key
            value: Hint value
            meta: Hint metadata
            if_match_version: Optional version for optimistic concurrency

        Returns:
            The created or updated hint

        Raises:
            NudgeStoreError: On conflicts or quota exceeded
        """
        # Check quota for new components
        if component not in self.store.components:
            if len(self.store.components) >= self.max_components:
                raise NudgeStoreError(
                    ErrorCode.E_QUOTA,
                    f"Maximum components ({self.max_components}) exceeded",
                    {"limit": self.max_components},
                )
            self.store.components[component] = ComponentHints()

        comp_hints = self.store.components[component]

        # Check if updating existing hint
        if key in comp_hints.hints:
            existing = comp_hints.hints[key]

            # Check version conflict
            if if_match_version is not None and existing.version != if_match_version:
                raise NudgeStoreError(
                    ErrorCode.E_CONFLICT,
                    f"Version mismatch: expected {if_match_version}, got {existing.version}",
                    {
                        "expected_version": if_match_version,
                        "current_version": existing.version,
                    },
                )

            # Update existing hint
            existing.value = value
            if meta:
                existing.meta = meta
            existing.version += 1
            existing.updated_at = datetime.utcnow().isoformat()
            return existing

        # Creating new hint - check quota
        total_hints = sum(len(c.hints) for c in self.store.components.values())
        if total_hints >= self.max_total_hints:
            raise NudgeStoreError(
                ErrorCode.E_QUOTA,
                f"Maximum total hints ({self.max_total_hints}) exceeded",
                {"limit": self.max_total_hints},
            )

        if len(comp_hints.hints) >= self.max_hints_per_component:
            raise NudgeStoreError(
                ErrorCode.E_QUOTA,
                f"Maximum hints per component ({self.max_hints_per_component}) exceeded",
                {"limit": self.max_hints_per_component},
            )

        # Create new hint
        hint = Hint(
            value=value,
            meta=meta or HintMeta(),
            version=1,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        comp_hints.hints[key] = hint
        return hint

    def get_hint(self, component: str, key: str) -> Optional[Hint]:
        """
        Get a hint by component and key.

        Args:
            component: Component name
            key: Hint key

        Returns:
            The hint if found, None otherwise
        """
        if component not in self.store.components:
            return None
        return self.store.components[component].hints.get(key)

    def delete_hint(self, component: str, key: str) -> Tuple[bool, Optional[Hint]]:
        """
        Delete a hint.

        Args:
            component: Component name
            key: Hint key

        Returns:
            Tuple of (deleted, previous_hint)
        """
        if component not in self.store.components:
            return False, None

        comp_hints = self.store.components[component]
        if key not in comp_hints.hints:
            return False, None

        previous = comp_hints.hints.pop(key)

        # Clean up empty components
        if not comp_hints.hints:
            del self.store.components[component]

        return True, previous

    def bump(self, component: str, key: str, delta: int = 1) -> Optional[Hint]:
        """
        Increase frecency counter for a hint.

        Args:
            component: Component name
            key: Hint key
            delta: Amount to increment use_count

        Returns:
            The updated hint, or None if not found
        """
        hint = self.get_hint(component, key)
        if not hint:
            return None

        hint.use_count += delta
        hint.last_used_at = datetime.utcnow().isoformat()
        return hint

    def list_components(self) -> List[Dict[str, any]]:
        """
        List all components with hint counts.

        Returns:
            List of component info dicts
        """
        return [
            {"name": name, "hint_count": len(comp.hints)}
            for name, comp in self.store.components.items()
        ]

    def get_all_hints(self, component: Optional[str] = None) -> List[Tuple[str, str, Hint]]:
        """
        Get all hints, optionally filtered by component.

        Args:
            component: Optional component name to filter

        Returns:
            List of (component, key, hint) tuples
        """
        results = []
        components = (
            {component: self.store.components[component]}
            if component and component in self.store.components
            else self.store.components
        )

        for comp_name, comp_hints in components.items():
            for key, hint in comp_hints.hints.items():
                results.append((comp_name, key, hint))

        return results

    def export_store(self) -> Dict:
        """
        Export the entire store as a dictionary.

        Returns:
            Store data as dict
        """
        return {
            "schema_version": self.store.schema_version,
            "created_at": self.store.created_at,
            "session_id": self.store.session_id,
            "components": {
                name: {"hints": {k: self._hint_to_dict(h) for k, h in comp.hints.items()}}
                for name, comp in self.store.components.items()
            },
        }

    def import_store(self, data: Dict, mode: str = "merge") -> Tuple[int, int]:
        """
        Import hints from a dictionary.

        Args:
            data: Store data dict
            mode: Import mode ("merge" or "replace")

        Returns:
            Tuple of (imported_count, skipped_count)

        Raises:
            NudgeStoreError: On invalid schema version or data
        """
        if data.get("schema_version") != "1.0":
            raise NudgeStoreError(
                ErrorCode.E_INVALID,
                f"Unsupported schema version: {data.get('schema_version')}",
            )

        if mode == "replace":
            self.store.components.clear()

        imported = 0
        skipped = 0

        components_data = data.get("components", {})
        for comp_name, comp_data in components_data.items():
            hints_data = comp_data.get("hints", {})
            for key, hint_data in hints_data.items():
                try:
                    # Skip if exists and mode is merge
                    if mode == "merge" and self.get_hint(comp_name, key):
                        skipped += 1
                        continue

                    hint = self._dict_to_hint(hint_data)
                    if comp_name not in self.store.components:
                        self.store.components[comp_name] = ComponentHints()
                    self.store.components[comp_name].hints[key] = hint
                    imported += 1
                except Exception:
                    skipped += 1

        return imported, skipped

    def _parse_iso_duration(self, duration: str) -> Optional[timedelta]:
        """
        Parse ISO-8601 duration string (e.g., PT2H, PT30M).

        Args:
            duration: ISO-8601 duration string

        Returns:
            timedelta if valid, None otherwise
        """
        # Simple parser for PT[hours]H[minutes]M[seconds]S format
        match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration)
        if not match:
            return None

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def _is_expired(self, hint: Hint) -> bool:
        """
        Check if a hint has expired based on TTL.

        Args:
            hint: Hint to check

        Returns:
            True if expired, False otherwise
        """
        if not hint.meta or not hint.meta.ttl:
            return False

        ttl = hint.meta.ttl

        # "session" TTL never expires during the session
        if ttl == "session":
            return False

        # Parse ISO-8601 duration
        duration = self._parse_iso_duration(ttl)
        if not duration:
            return False  # Invalid duration, treat as non-expiring

        # Check if time since creation exceeds duration
        created = datetime.fromisoformat(hint.created_at)
        now = datetime.utcnow()
        return (now - created) > duration

    def evict_expired(self) -> int:
        """
        Remove all expired hints from the store.

        Returns:
            Number of hints evicted
        """
        evicted = 0
        components_to_remove = []

        for comp_name, comp_hints in self.store.components.items():
            keys_to_remove = []

            for key, hint in comp_hints.hints.items():
                if self._is_expired(hint):
                    keys_to_remove.append(key)

            # Remove expired hints
            for key in keys_to_remove:
                del comp_hints.hints[key]
                evicted += 1

            # Mark empty components for removal
            if not comp_hints.hints:
                components_to_remove.append(comp_name)

        # Remove empty components
        for comp_name in components_to_remove:
            del self.store.components[comp_name]

        return evicted

    def _hint_to_dict(self, hint: Hint) -> Dict:
        """Convert a Hint to a dictionary."""
        # Handle HintValue serialization
        value = hint.value
        if isinstance(value, str):
            value_dict = value
        elif hasattr(value, "__dict__"):
            value_dict = {k: v for k, v in value.__dict__.items() if v is not None}
        else:
            value_dict = value

        # Handle HintMeta serialization
        meta_dict = {}
        if hint.meta:
            for k, v in hint.meta.__dict__.items():
                if v is None:
                    continue
                if hasattr(v, "__dict__"):
                    # Handle nested objects like Scope
                    meta_dict[k] = {
                        kk: vv for kk, vv in v.__dict__.items() if vv is not None
                    }
                else:
                    meta_dict[k] = v

        return {
            "value": value_dict,
            "meta": meta_dict,
            "version": hint.version,
            "created_at": hint.created_at,
            "updated_at": hint.updated_at,
            "last_used_at": hint.last_used_at,
            "use_count": hint.use_count,
        }

    def _dict_to_hint(self, data: Dict) -> Hint:
        """Convert a dictionary to a Hint."""
        # Basic reconstruction - simplified for now
        return Hint(
            value=data.get("value", ""),
            meta=HintMeta(),  # TODO: Reconstruct meta properly
            version=data.get("version", 1),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            last_used_at=data.get("last_used_at"),
            use_count=data.get("use_count", 0),
        )
