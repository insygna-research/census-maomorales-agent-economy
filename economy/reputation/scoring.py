"""Reputation scoring algorithms."""

import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from economy.models import PerformanceRecord, ReputationSummary


class ReputationScorer(ABC):
    """Base class for reputation scoring algorithms."""

    @abstractmethod
    def compute_summary(
        self, agent_id: str, history: list[PerformanceRecord]
    ) -> ReputationSummary:
        """Compute a reputation summary from performance history."""
        pass

    def score(self, history: list[PerformanceRecord]) -> float:
        """Compute just the overall score."""
        if not history:
            return 0.5  # Default for new agents
        summary = self.compute_summary("temp", history)
        return summary.overall_score


class SimpleReputationScorer(ReputationScorer):
    """
    Simple weighted average reputation scorer.

    Score = w1*completion_rate + w2*on_time_rate + w3*quality + w4*satisfaction
    """

    def __init__(
        self,
        completion_weight: float = 0.3,
        on_time_weight: float = 0.2,
        quality_weight: float = 0.4,
        satisfaction_weight: float = 0.1,
    ) -> None:
        self.weights = {
            "completion": completion_weight,
            "on_time": on_time_weight,
            "quality": quality_weight,
            "satisfaction": satisfaction_weight,
        }
        # Normalize weights
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}

    def compute_summary(
        self, agent_id: str, history: list[PerformanceRecord]
    ) -> ReputationSummary:
        if not history:
            return ReputationSummary(
                agent_id=agent_id,
                overall_score=0.5,
                confidence=0.0,
            )

        # Compute component metrics
        total = len(history)
        completed = sum(1 for r in history if r.completed)
        # Only count on_time for completed tasks
        on_time = sum(1 for r in history if r.completed and r.on_time)
        
        completion_rate = completed / total
        on_time_rate = on_time / completed if completed > 0 else 0.0

        # Average quality (only for completed tasks)
        quality_scores = [r.quality_score for r in history if r.completed and r.quality_score > 0]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5

        # Average satisfaction (if available)
        satisfaction_scores = [
            r.publisher_satisfaction
            for r in history
            if r.publisher_satisfaction is not None
        ]
        avg_satisfaction = (
            sum(satisfaction_scores) / len(satisfaction_scores)
            if satisfaction_scores
            else 0.5
        )

        # Compute weighted score
        overall_score = (
            self.weights["completion"] * completion_rate
            + self.weights["on_time"] * on_time_rate
            + self.weights["quality"] * avg_quality
            + self.weights["satisfaction"] * avg_satisfaction
        )

        # Confidence based on sample size (more data = more confidence)
        confidence = min(1.0, total / 20)  # Full confidence at 20 tasks

        # Duration accuracy
        duration_accuracies = [
            r.duration_accuracy for r in history if r.duration_accuracy is not None
        ]
        avg_duration_accuracy = (
            sum(duration_accuracies) / len(duration_accuracies)
            if duration_accuracies
            else 0.5
        )

        # Economic metrics
        total_earnings = sum(r.final_price for r in history if r.completed)
        avg_price = total_earnings / completed if completed > 0 else 0.0

        # Time-based metrics
        first_task = min(r.timestamp for r in history)
        age_days = (datetime.utcnow() - first_task).days

        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_activity = sum(1 for r in history if r.timestamp > week_ago)

        # Per-capability scores
        capability_scores: dict[str, float] = {}
        capability_records: dict[str, list[PerformanceRecord]] = {}
        for record in history:
            for cap in record.required_capabilities:
                if cap not in capability_records:
                    capability_records[cap] = []
                capability_records[cap].append(record)
        
        for cap, records in capability_records.items():
            cap_completed = sum(1 for r in records if r.completed)
            cap_quality = [r.quality_score for r in records if r.completed]
            if cap_completed > 0:
                capability_scores[cap] = sum(cap_quality) / len(cap_quality) if cap_quality else 0.5
            else:
                capability_scores[cap] = 0.0

        return ReputationSummary(
            agent_id=agent_id,
            overall_score=overall_score,
            completion_rate=completion_rate,
            on_time_rate=on_time_rate,
            average_quality=avg_quality,
            duration_accuracy=avg_duration_accuracy,
            average_satisfaction=avg_satisfaction if satisfaction_scores else None,
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=total - completed,
            total_earnings=total_earnings,
            average_price=avg_price,
            capability_scores=capability_scores,
            age_days=age_days,
            recent_activity=recent_activity,
            confidence=confidence,
        )


class DecayingReputationScorer(ReputationScorer):
    """
    Reputation scorer that weights recent performance more heavily.

    Uses exponential decay so recent tasks matter more than old ones.
    """

    def __init__(
        self,
        half_life_days: float = 30,
        base_scorer: ReputationScorer | None = None,
    ) -> None:
        """
        Args:
            half_life_days: Days until a record's weight halves
            base_scorer: Underlying scorer for computing component scores
        """
        self.half_life_days = half_life_days
        self.decay_rate = math.log(2) / half_life_days
        self.base_scorer = base_scorer or SimpleReputationScorer()

    def _compute_weight(self, record: PerformanceRecord) -> float:
        """Compute decay weight for a record."""
        age_days = (datetime.utcnow() - record.timestamp).total_seconds() / 86400
        return math.exp(-self.decay_rate * age_days)

    def compute_summary(
        self, agent_id: str, history: list[PerformanceRecord]
    ) -> ReputationSummary:
        if not history:
            return ReputationSummary(
                agent_id=agent_id,
                overall_score=0.5,
                confidence=0.0,
            )

        # Get base summary for structure
        base_summary = self.base_scorer.compute_summary(agent_id, history)

        # Compute weighted metrics
        weights = [self._compute_weight(r) for r in history]
        total_weight = sum(weights)

        if total_weight == 0:
            return base_summary

        # Weighted completion rate
        weighted_completed = sum(
            w for w, r in zip(weights, history) if r.completed
        )
        weighted_completion_rate = weighted_completed / total_weight

        # Weighted quality
        quality_weights = [(w, r.quality_score) for w, r in zip(weights, history) if r.completed]
        if quality_weights:
            weighted_quality = sum(w * q for w, q in quality_weights) / sum(w for w, _ in quality_weights)
        else:
            weighted_quality = 0.5

        # Combine into overall score
        overall_score = 0.4 * weighted_completion_rate + 0.6 * weighted_quality

        # Update the summary with decayed values
        base_summary.overall_score = overall_score
        base_summary.average_quality = weighted_quality

        return base_summary


class BayesianReputationScorer(ReputationScorer):
    """
    Bayesian reputation scorer for handling cold-start problem.

    Uses a prior distribution and updates based on evidence.
    New agents start with a prior that shifts toward their true performance
    as they complete more tasks.
    """

    def __init__(
        self,
        prior_alpha: float = 2.0,
        prior_beta: float = 2.0,
    ) -> None:
        """
        Args:
            prior_alpha: Beta distribution alpha parameter (pseudo-successes)
            prior_beta: Beta distribution beta parameter (pseudo-failures)
        """
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta

    def compute_summary(
        self, agent_id: str, history: list[PerformanceRecord]
    ) -> ReputationSummary:
        if not history:
            # Return prior mean
            prior_mean = self.prior_alpha / (self.prior_alpha + self.prior_beta)
            return ReputationSummary(
                agent_id=agent_id,
                overall_score=prior_mean,
                confidence=0.0,
            )

        # Count successes (completed with quality >= 0.5)
        successes = sum(
            1 for r in history if r.completed and r.quality_score >= 0.5
        )
        failures = len(history) - successes

        # Posterior parameters
        alpha = self.prior_alpha + successes
        beta = self.prior_beta + failures

        # Posterior mean as reputation
        overall_score = alpha / (alpha + beta)

        # Confidence based on total observations
        confidence = min(1.0, len(history) / 20)

        # Get detailed stats from simple scorer
        simple_scorer = SimpleReputationScorer()
        base_summary = simple_scorer.compute_summary(agent_id, history)

        # Override with Bayesian score
        base_summary.overall_score = overall_score
        base_summary.confidence = confidence
        base_summary.metadata["bayesian_alpha"] = alpha
        base_summary.metadata["bayesian_beta"] = beta

        return base_summary
