"""Reputation ledger - stores and manages performance history."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from ulid import ULID

from economy.models import (
    Execution,
    ExecutionStatus,
    PerformanceRecord,
    ReputationSummary,
    Task,
)
from economy.reputation.scoring import ReputationScorer, SimpleReputationScorer


class ReputationLedger:
    """
    Central ledger for agent performance and reputation.

    Stores performance records in append-only fashion and computes
    reputation scores on demand or periodically.
    """

    def __init__(
        self,
        scorer: ReputationScorer | None = None,
        cache_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        """
        Initialize the reputation ledger.

        Args:
            scorer: Reputation scoring algorithm to use
            cache_ttl: How long to cache reputation summaries
        """
        self.scorer = scorer or SimpleReputationScorer()
        self.cache_ttl = cache_ttl

        # In-memory storage (will be backed by DB in production)
        self._records: dict[str, list[PerformanceRecord]] = defaultdict(list)
        self._summaries: dict[str, ReputationSummary] = {}
        self._summary_timestamps: dict[str, datetime] = {}

    def record_performance(
        self,
        agent_id: str,
        task: Task,
        execution: Execution,
        quality_score: float = 0.0,
        publisher_satisfaction: float | None = None,
    ) -> PerformanceRecord:
        """
        Record an agent's performance on a task.

        Args:
            agent_id: The agent's ID
            task: The task that was executed
            execution: The execution record
            quality_score: Quality score from evaluation (0-1)
            publisher_satisfaction: Optional satisfaction rating (0-1)

        Returns:
            The created PerformanceRecord
        """
        # Determine if completed and on time
        completed = execution.status == ExecutionStatus.COMPLETED
        on_time = True
        if task.deadline and execution.completed_at:
            on_time = execution.completed_at <= task.deadline

        # Get duration info from the bid
        from economy.models import Bid

        # Find the bid
        estimated_duration = timedelta(hours=1)  # Default
        bid_price = execution.agreed_price

        record = PerformanceRecord(
            record_id=str(ULID()),
            agent_id=agent_id,
            task_id=task.task_id,
            execution_id=execution.execution_id,
            timestamp=datetime.utcnow(),
            completed=completed,
            on_time=on_time,
            estimated_duration=estimated_duration,
            actual_duration=execution.duration,
            quality_score=quality_score,
            bid_price=bid_price,
            final_price=execution.agreed_price,
            publisher_satisfaction=publisher_satisfaction,
            task_type=task.specification.required_capabilities[0]
            if task.specification.required_capabilities
            else "unknown",
            required_capabilities=task.specification.required_capabilities,
        )

        self._records[agent_id].append(record)

        # Invalidate cached summary
        self._summary_timestamps.pop(agent_id, None)

        return record

    def add_record(self, record: PerformanceRecord) -> None:
        """Add a pre-built performance record."""
        self._records[record.agent_id].append(record)
        self._summary_timestamps.pop(record.agent_id, None)

    def get_history(
        self, agent_id: str, limit: int = 100
    ) -> list[PerformanceRecord]:
        """Get performance history for an agent."""
        records = self._records.get(agent_id, [])
        # Sort by timestamp descending
        sorted_records = sorted(records, key=lambda r: r.timestamp, reverse=True)
        return sorted_records[:limit]

    def get_all_records(self) -> list[PerformanceRecord]:
        """Get all performance records."""
        all_records = []
        for records in self._records.values():
            all_records.extend(records)
        return sorted(all_records, key=lambda r: r.timestamp, reverse=True)

    def get_summary(self, agent_id: str, force_refresh: bool = False) -> ReputationSummary:
        """
        Get reputation summary for an agent.

        Uses caching to avoid recomputing on every call.
        """
        now = datetime.utcnow()

        # Check cache
        if not force_refresh and agent_id in self._summaries:
            cache_time = self._summary_timestamps.get(agent_id)
            if cache_time and (now - cache_time) < self.cache_ttl:
                return self._summaries[agent_id]

        # Compute fresh summary
        history = self.get_history(agent_id, limit=1000)
        summary = self.scorer.compute_summary(agent_id, history)

        # Cache it
        self._summaries[agent_id] = summary
        self._summary_timestamps[agent_id] = now

        return summary

    def get_score(self, agent_id: str) -> float:
        """Get just the reputation score for an agent."""
        summary = self.get_summary(agent_id)
        return summary.overall_score

    def get_all_scores(self) -> dict[str, float]:
        """Get reputation scores for all known agents."""
        return {
            agent_id: self.get_score(agent_id)
            for agent_id in self._records.keys()
        }

    def get_all_summaries(self) -> list[ReputationSummary]:
        """Get reputation summaries for all known agents."""
        return [
            self.get_summary(agent_id)
            for agent_id in self._records.keys()
        ]

    def get_leaderboard(self, limit: int = 10) -> list[ReputationSummary]:
        """Get top agents by reputation."""
        summaries = self.get_all_summaries()
        # Sort by score descending
        sorted_summaries = sorted(
            summaries, key=lambda s: s.overall_score, reverse=True
        )
        return sorted_summaries[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get overall reputation system statistics."""
        all_records = self.get_all_records()
        summaries = self.get_all_summaries()

        if not all_records:
            return {
                "agents_tracked": 0,
                "total_records": 0,
                "average_score": 0.5,
                "completion_rate": 0.0,
            }

        scores = [s.overall_score for s in summaries]
        completed = sum(1 for r in all_records if r.completed)

        return {
            "agents_tracked": len(self._records),
            "total_records": len(all_records),
            "average_score": sum(scores) / len(scores) if scores else 0.5,
            "score_distribution": {
                "min": min(scores) if scores else 0,
                "max": max(scores) if scores else 1,
                "median": sorted(scores)[len(scores) // 2] if scores else 0.5,
            },
            "completion_rate": completed / len(all_records) if all_records else 0,
            "total_quality_recorded": sum(r.quality_score for r in all_records),
        }

    def clear(self) -> None:
        """Clear all records (for testing)."""
        self._records.clear()
        self._summaries.clear()
        self._summary_timestamps.clear()
