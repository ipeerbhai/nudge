"""Scoring and ranking algorithm for hints."""

import math
from datetime import datetime
from typing import List, Optional
from .models import Hint, HintMatch, MatchExplanation, NudgeContext
from .matching import Matcher


class Scorer:
    """Handles hint scoring and ranking."""

    # Weights for the scoring formula
    WEIGHT_FRECENCY = 0.30
    WEIGHT_PRIORITY = 0.20
    WEIGHT_CONFIDENCE = 0.20
    WEIGHT_SPECIFICITY = 0.20
    WEIGHT_RECENCY = 0.10

    @staticmethod
    def calculate_frecency(use_count: int, last_used_at: Optional[str]) -> float:
        """
        Calculate frecency score based on use count and recency.

        Uses exponential decay on use_count with time since last use.

        Args:
            use_count: Number of times hint was used
            last_used_at: ISO timestamp of last use

        Returns:
            Frecency score between 0.0 and 1.0
        """
        if use_count == 0:
            return 0.0

        # Base score from use count (with diminishing returns)
        base_score = 1.0 - math.exp(-use_count / 10.0)

        # Apply time decay if we have last_used_at
        if last_used_at:
            try:
                last_used = datetime.fromisoformat(last_used_at)
                now = datetime.utcnow()
                hours_since = (now - last_used).total_seconds() / 3600.0

                # Decay factor: 50% after 7 days, 90% after 30 days
                decay = math.exp(-hours_since / (7 * 24))
                base_score *= decay
            except (ValueError, AttributeError):
                pass  # Invalid timestamp, use base score

        return base_score

    @staticmethod
    def calculate_recency(updated_at: str) -> float:
        """
        Calculate recency score based on when hint was last updated.

        Args:
            updated_at: ISO timestamp of last update

        Returns:
            Recency score between 0.0 and 1.0
        """
        try:
            updated = datetime.fromisoformat(updated_at)
            now = datetime.utcnow()
            hours_since = (now - updated).total_seconds() / 3600.0

            # Recent updates get higher scores
            # 100% if within 1 hour, 50% after 7 days, 10% after 30 days
            return math.exp(-hours_since / (7 * 24))
        except (ValueError, AttributeError):
            return 0.5  # Default for invalid timestamps

    @staticmethod
    def score_hint(hint: Hint, context: NudgeContext, match_reasons: List[str]) -> float:
        """
        Calculate overall score for a hint.

        Score formula:
        score = 0.30 * frecency + 0.20 * priority + 0.20 * confidence
                + 0.20 * specificity + 0.10 * recency

        Args:
            hint: The hint to score
            context: Current context
            match_reasons: Reasons why hint matched (from eligibility check)

        Returns:
            Overall score between 0.0 and 1.0
        """
        # Frecency component
        frecency = Scorer.calculate_frecency(hint.use_count, hint.last_used_at)

        # Priority component (normalize to 0-1, default 5)
        priority = (hint.meta.priority or 5) / 10.0 if hint.meta else 0.5

        # Confidence component (default 0.5)
        confidence = hint.meta.confidence or 0.5 if hint.meta else 0.5

        # Scope specificity component
        specificity_count = Matcher.count_scope_specificity(
            hint.meta.scope if hint.meta else None
        )
        # Normalize: 0 fields = 0.0, 5+ fields = 1.0
        specificity = min(specificity_count / 5.0, 1.0)

        # Recency component
        recency = Scorer.calculate_recency(hint.updated_at)

        # Calculate weighted score
        score = (
            Scorer.WEIGHT_FRECENCY * frecency
            + Scorer.WEIGHT_PRIORITY * priority
            + Scorer.WEIGHT_CONFIDENCE * confidence
            + Scorer.WEIGHT_SPECIFICITY * specificity
            + Scorer.WEIGHT_RECENCY * recency
        )

        return score

    @staticmethod
    def create_match_explanation(
        hint: Hint, context: NudgeContext, score: float, match_reasons: List[str]
    ) -> MatchExplanation:
        """
        Create a detailed explanation of why a hint matched.

        Args:
            hint: The hint
            context: Current context
            score: Calculated score
            match_reasons: Reasons from eligibility check

        Returns:
            MatchExplanation with score and detailed reasons
        """
        reasons = list(match_reasons)  # Copy the match reasons

        # Add frecency info if relevant
        if hint.use_count > 0:
            if hint.last_used_at:
                try:
                    last_used = datetime.fromisoformat(hint.last_used_at)
                    now = datetime.utcnow()
                    delta = now - last_used

                    if delta.total_seconds() < 300:  # 5 minutes
                        reasons.append(
                            f"recently used ({int(delta.total_seconds() / 60)}m ago)"
                        )
                    elif delta.total_seconds() < 3600:  # 1 hour
                        reasons.append(
                            f"used {int(delta.total_seconds() / 60)} minutes ago"
                        )
                    elif delta.days == 0:
                        reasons.append(
                            f"used {int(delta.total_seconds() / 3600)} hours ago"
                        )
                    elif delta.days == 1:
                        reasons.append("used yesterday")
                    else:
                        reasons.append(f"used {delta.days} days ago")
                except (ValueError, AttributeError):
                    pass

            reasons.append(f"used {hint.use_count} time{'s' if hint.use_count != 1 else ''}")

        # Add priority if high
        if hint.meta and hint.meta.priority and hint.meta.priority >= 8:
            reasons.append(f"high priority ({hint.meta.priority}/10)")

        # Add confidence if high
        if hint.meta and hint.meta.confidence and hint.meta.confidence >= 0.8:
            reasons.append(f"high confidence ({hint.meta.confidence:.1f})")

        return MatchExplanation(matched=True, score=round(score, 2), reasons=reasons)

    @staticmethod
    def rank_hints(
        hints: List[tuple[str, str, Hint]], context: NudgeContext
    ) -> List[HintMatch]:
        """
        Rank a list of hints by score.

        Args:
            hints: List of (component, key, hint) tuples
            context: Current context

        Returns:
            Sorted list of HintMatch objects (highest score first)
        """
        matches = []

        for component, key, hint in hints:
            # Check eligibility
            is_eligible, match_reasons = Matcher.is_eligible(hint, context)
            if not is_eligible:
                continue

            # Calculate score
            score = Scorer.score_hint(hint, context, match_reasons)

            # Create explanation
            explanation = Scorer.create_match_explanation(
                hint, context, score, match_reasons
            )

            matches.append(
                HintMatch(hint=hint, score=score, match_explain=explanation)
            )

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches
