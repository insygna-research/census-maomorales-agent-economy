"""Tests for auction mechanisms."""

import pytest
from datetime import datetime, timedelta

from economy.models import (
    AllocationMethod,
    Bid,
    Budget,
    Task,
    TaskSpec,
)
from economy.market.auctions import AuctionEngine


@pytest.fixture
def sample_task():
    return Task(
        task_id="task-1",
        publisher_id="user-1",
        specification=TaskSpec(
            title="Test Task",
            description="A test task",
        ),
        budget=Budget(min_price=1.0, max_price=10.0),
        allocation_method=AllocationMethod.FIRST_PRICE_AUCTION,
    )


@pytest.fixture
def sample_bids():
    return [
        Bid(bid_id="bid-1", task_id="task-1", agent_id="agent-1", price=8.0),
        Bid(bid_id="bid-2", task_id="task-1", agent_id="agent-2", price=5.0),
        Bid(bid_id="bid-3", task_id="task-1", agent_id="agent-3", price=7.0),
    ]


class TestAuctionEngine:
    def test_first_price_auction(self, sample_task, sample_bids):
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, sample_bids)

        assert result.has_winner
        assert result.winner_id == "agent-2"  # Lowest bid
        assert result.final_price == 5.0  # Pays bid price
        assert result.mechanism_used == AllocationMethod.FIRST_PRICE_AUCTION

    def test_second_price_auction(self, sample_task, sample_bids):
        sample_task.allocation_method = AllocationMethod.SECOND_PRICE_AUCTION
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, sample_bids)

        assert result.has_winner
        assert result.winner_id == "agent-2"  # Lowest bid
        assert result.final_price == 7.0  # Pays second-lowest price
        assert result.mechanism_used == AllocationMethod.SECOND_PRICE_AUCTION

    def test_second_price_single_bid(self, sample_task):
        sample_task.allocation_method = AllocationMethod.SECOND_PRICE_AUCTION
        bids = [Bid(bid_id="bid-1", task_id="task-1", agent_id="agent-1", price=5.0)]
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, bids)

        assert result.has_winner
        assert result.winner_id == "agent-1"
        assert result.final_price == 5.0  # Only one bid, pays their bid

    def test_fixed_price_allocation(self, sample_task, sample_bids):
        sample_task.allocation_method = AllocationMethod.FIXED_PRICE
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, sample_bids)

        assert result.has_winner
        # First bid within budget wins
        assert result.mechanism_used == AllocationMethod.FIXED_PRICE

    def test_reputation_weighted_auction(self, sample_task, sample_bids):
        sample_task.allocation_method = AllocationMethod.REPUTATION_WEIGHTED
        engine = AuctionEngine(reputation_weight=0.5)

        # Agent 1 has high reputation but high price
        # Agent 2 has low reputation but low price
        # Agent 3 has medium reputation and medium price
        reputation_scores = {
            "agent-1": 0.9,
            "agent-2": 0.3,
            "agent-3": 0.7,
        }

        result = engine.run_auction(sample_task, sample_bids, reputation_scores)

        assert result.has_winner
        assert result.mechanism_used == AllocationMethod.REPUTATION_WEIGHTED
        # Winner depends on weight balance

    def test_no_bids(self, sample_task):
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, [])

        assert not result.has_winner
        assert result.winner_id is None
        assert result.winning_bid is None

    def test_bids_over_budget(self, sample_task):
        # All bids exceed budget
        over_budget_bids = [
            Bid(bid_id="bid-1", task_id="task-1", agent_id="agent-1", price=15.0),
            Bid(bid_id="bid-2", task_id="task-1", agent_id="agent-2", price=20.0),
        ]
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, over_budget_bids)

        assert not result.has_winner

    def test_tie_breaking(self, sample_task):
        # Two identical bids - earlier one should win
        now = datetime.utcnow()
        tied_bids = [
            Bid(
                bid_id="bid-1",
                task_id="task-1",
                agent_id="agent-1",
                price=5.0,
                submitted_at=now + timedelta(seconds=1),
            ),
            Bid(
                bid_id="bid-2",
                task_id="task-1",
                agent_id="agent-2",
                price=5.0,
                submitted_at=now,  # Earlier
            ),
        ]
        engine = AuctionEngine()
        result = engine.run_auction(sample_task, tied_bids)

        assert result.has_winner
        assert result.winner_id == "agent-2"  # Earlier bid wins tie
