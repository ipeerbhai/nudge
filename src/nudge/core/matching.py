"""Context matching and eligibility filtering."""

from typing import List, Optional
from wcmatch import glob
from .models import Hint, NudgeContext, Scope


class Matcher:
    """Handles context matching for hint eligibility."""

    @staticmethod
    def is_eligible(hint: Hint, context: NudgeContext) -> tuple[bool, List[str]]:
        """
        Check if a hint is eligible given a context.

        All scope conditions must match for eligibility.

        Args:
            hint: The hint to check
            context: The current context

        Returns:
            Tuple of (is_eligible, match_reasons)
        """
        if not hint.meta or not hint.meta.scope:
            # No scope means always eligible
            return True, ["no scope restrictions"]

        scope = hint.meta.scope
        reasons = []

        # Check cwd_glob
        if scope.cwd_glob and context.cwd:
            if not Matcher._match_cwd_glob(scope.cwd_glob, context.cwd):
                return False, []
            matched_pattern = Matcher._get_matched_pattern(scope.cwd_glob, context.cwd)
            if matched_pattern:
                reasons.append(f"cwd matched {matched_pattern}")

        # Check repo
        if scope.repo and context.repo:
            if not Matcher._match_repo(scope.repo, context.repo):
                return False, []
            reasons.append(f"repo matched")

        # Check branch
        if scope.branch and context.branch:
            if context.branch not in scope.branch:
                return False, []
            reasons.append(f"branch={context.branch} allowed")

        # Check os
        if scope.os and context.os:
            if context.os not in scope.os:
                return False, []
            reasons.append(f"os={context.os.value} matched")

        # Check env_required
        if scope.env_required and context.env:
            missing = [
                name for name in scope.env_required if name not in context.env
            ]
            if missing:
                return False, []
            if scope.env_required:
                reasons.append(f"required env vars present: {', '.join(scope.env_required)}")

        # Check env_match
        if scope.env_match and context.env:
            for key, expected in scope.env_match.items():
                actual = context.env.get(key)
                if actual is None:
                    return False, []

                # expected can be a string or list of strings
                if isinstance(expected, list):
                    if actual not in expected:
                        return False, []
                else:
                    if actual != expected:
                        return False, []

            if scope.env_match:
                reasons.append(f"env values matched")

        # If we got here, all conditions passed
        if not reasons:
            reasons.append("all scope conditions matched")

        return True, reasons

    @staticmethod
    def _match_cwd_glob(patterns: List[str], cwd: str) -> bool:
        """Check if cwd matches any of the glob patterns."""
        for pattern in patterns:
            if glob.globmatch(cwd, pattern, flags=glob.GLOBSTAR | glob.BRACE):
                return True
        return False

    @staticmethod
    def _get_matched_pattern(patterns: List[str], cwd: str) -> Optional[str]:
        """Get the first pattern that matches cwd."""
        for pattern in patterns:
            if glob.globmatch(cwd, pattern, flags=glob.GLOBSTAR | glob.BRACE):
                return pattern
        return None

    @staticmethod
    def _match_repo(scope_repo: any, context_repo: str) -> bool:
        """Check if context repo matches scope repo."""
        if isinstance(scope_repo, list):
            return context_repo in scope_repo
        return context_repo == scope_repo

    @staticmethod
    def count_scope_specificity(scope: Optional[Scope]) -> int:
        """
        Count how many scope fields are specified.

        More specific scopes get higher scores.

        Args:
            scope: The scope to analyze

        Returns:
            Count of specified scope fields
        """
        if not scope:
            return 0

        count = 0
        if scope.cwd_glob:
            count += 1
        if scope.repo:
            count += 1
        if scope.branch:
            count += 1
        if scope.os:
            count += 1
        if scope.env_required:
            count += len(scope.env_required)
        if scope.env_match:
            count += len(scope.env_match)

        return count
