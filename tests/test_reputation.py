"""Tests for reputation system."""

import pytest
from datetime import datetime, timedelta

from economy.models import PerformanceRecord
from economy.reputation.ledger import ReputationLedger
from economy.reputation.scoring import (
    SimpleReputationScorer,
    DecayingReputationScorer,
    BayesianReputationScorer,
)


def create_performance_record(
    agent_id: str = "agent-1",
    completed: bool = True,
    on_time: bool = True,
    quality_score: float = 0.8,
    days_ago: int = 0,
) -> PerformanceRecord:
    return PerformanceRecord(
        record_id=f"record-{datetime.utcnow().timestamp()}",
        agent_id=agent_id,
        task_id="task-1",
        execution_id="exec-1",
        timestamp=datetime.utcnow() - timedelta(days=days_ago),
        completed=completed,
        on_time=on_time,
        estimated_duration=timedelta(hours=1),
        actual_duration=timedelta(hours=1),
        quality_score=quality_score,
        bid_price=5.0,
        final_price=5.0,
    )


class TestSimpleReputationScorer:
    def test_empty_history(self):
        scorer = SimpleReputationScorer()
        summary = scorer.compute_summary("agent-1", [])
        assert summary.overall_score == 0.5  # Default
        assert summary.confidence == 0.0

    def test_perfect_history(self):
        scorer = SimpleReputationScorer()
        history = [
            create_performance_record(completed=True, on_time=True, quality_score=1.0)
            for _ in range(10)
        ]
        summary = scorer.compute_summary("agent-1", history)
        assert summary.overall_score > 0.9
        assert summary.completion_rate == 1.0
        assert summary.on_time_rate == 1.0

    def test_poor_history(self):
        scorer = SimpleReputationScorer()
        history = [
            create_performance_record(completed=False, on_time=False, quality_score=0.0)
            for _ in range(10)
        ]
        summary = scorer.compute_summary("agent-1", history)
        assert summary.overall_score < 0.3
        assert summary.completion_rate == 0.0

    def test_mixed_history(self):
        scorer = SimpleReputationScorer()
        history = [
            create_performance_record(completed=True, quality_score=0.8),
            create_performance_record(completed=True, quality_score=0.7),
            create_performance_record(completed=False, quality_score=0.0),
            create_performance_record(completed=True, quality_score=0.9),
        ]
        summary = scorer.compute_summary("agent-1", history)
        assert 0.4 < summary.overall_score < 0.8
        assert summary.completion_rate == 0.75

    def test_confidence_grows(self):
        scorer = SimpleReputationScorer()

        few_records = [create_performance_record() for _ in range(3)]
        many_records = [create_performance_record() for _ in range(25)]

        summary_few = scorer.compute_summary("agent-1", few_records)
        summary_many = scorer.compute_summary("agent-1", many_records)

        assert summary_many.confidence > summary_few.confidence
        assert summary_many.confidence == 1.0  # Max at 20 records


class TestDecayingReputationScorer:
    def test_recent_weighted_more(self):
        scorer = DecayingReputationScorer(half_life_days=7)

        # Old good records + recent bad record
        history = [
            create_performance_record(quality_score=0.9, days_ago=30),
            create_performance_record(quality_score=0.9, days_ago=25),
            create_performance_record(quality_score=0.9, days_ago=20),
            create_performance_record(quality_score=0.3, days_ago=1),  # Recent and bad
        ]

        summary = scorer.compute_summary("agent-1", history)

        # Recent bad performance should drag down the score
        assert summary.overall_score < 0.7


class TestBayesianReputationScorer:
    def test_prior_for_new_agent(self):
        scorer = BayesianReputationScorer(prior_alpha=2, prior_beta=2)
        summary = scorer.compute_summary("agent-1", [])
        # Prior mean = alpha / (alpha + beta) = 0.5
        assert summary.overall_score == 0.5

    def test_converges_with_data(self):
        scorer = BayesianReputationScorer(prior_alpha=2, prior_beta=2)

        # All successes should push score up
        history = [
            create_performance_record(completed=True, quality_score=0.9)
            for _ in range(20)
        ]

        summary = scorer.compute_summary("agent-1", history)
        # Should be close to 1.0 with many successes
        assert summary.overall_score > 0.85


class TestReputationLedger:
    def test_add_and_retrieve(self):
        ledger = ReputationLedger()
        record = create_performance_record("agent-1")
        ledger.add_record(record)

        history = ledger.get_history("agent-1")
        assert len(history) == 1
        assert history[0].agent_id == "agent-1"

    def test_get_summary(self):
        ledger = ReputationLedger()

        for i in range(5):
            ledger.add_record(create_performance_record("agent-1", quality_score=0.8))

        summary = ledger.get_summary("agent-1")
        assert summary.agent_id == "agent-1"
        assert summary.total_tasks == 5

    def test_get_all_scores(self):
        ledger = ReputationLedger()

        ledger.add_record(create_performance_record("agent-1", quality_score=0.9))
        ledger.add_record(create_performance_record("agent-2", quality_score=0.5))

        scores = ledger.get_all_scores()
        assert "agent-1" in scores
        assert "agent-2" in scores

    def test_leaderboard(self):
        ledger = ReputationLedger()

        # Agent 1: Good
        for _ in range(5):
            ledger.add_record(create_performance_record("agent-1", quality_score=0.9))

        # Agent 2: Bad
        for _ in range(5):
            ledger.add_record(create_performance_record("agent-2", quality_score=0.3))

        # Agent 3: Medium
        for _ in range(5):
            ledger.add_record(create_performance_record("agent-3", quality_score=0.6))

        leaderboard = ledger.get_leaderboard(limit=3)
        assert len(leaderboard) == 3
        assert leaderboard[0].agent_id == "agent-1"  # Best first
