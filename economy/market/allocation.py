"""Allocation strategies and task assignment."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ulid import ULID

from economy.models import (
    Bid,
    BidStatus,
    Execution,
    ExecutionStatus,
    Task,
    TaskStatus,
)
from economy.market.auctions import AuctionEngine, AuctionResult


class AllocationStrategy(ABC):
    """Base class for allocation strategies."""

    @abstractmethod
    async def allocate(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float],
    ) -> AuctionResult:
        """Allocate a task to an agent."""
        pass


class ImmediateAllocationStrategy(AllocationStrategy):
    """
    Allocate immediately when a valid bid is received.

    Good for fixed-price tasks where speed matters.
    """

    async def allocate(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float],
    ) -> AuctionResult:
        engine = AuctionEngine()
        return engine.run_auction(task, bids, reputation_scores)


class BatchAllocationStrategy(AllocationStrategy):
    """
    Collect bids for a period, then run auction.

    Good for competitive auctions where you want multiple bids.
    """

    def __init__(self, engine: AuctionEngine | None = None) -> None:
        self.engine = engine or AuctionEngine()

    async def allocate(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float],
    ) -> AuctionResult:
        return self.engine.run_auction(task, bids, reputation_scores)


class TaskAllocator:
    """
    Handles the complete task allocation lifecycle.

    This coordinates between the task board, auction engine,
    and creates execution records.
    """

    def __init__(
        self,
        auction_engine: AuctionEngine | None = None,
    ) -> None:
        self.engine = auction_engine or AuctionEngine()

    async def run_allocation(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float] | None = None,
    ) -> tuple[AuctionResult, Execution | None]:
        """
        Run allocation and create execution if winner found.

        Returns:
            Tuple of (AuctionResult, Execution or None)
        """
        reputation_scores = reputation_scores or {}

        # Run the auction
        result = self.engine.run_auction(task, bids, reputation_scores)

        if not result.has_winner:
            return result, None

        # Create execution record
        execution = Execution(
            execution_id=str(ULID()),
            task_id=task.task_id,
            agent_id=result.winner_id,
            bid_id=result.winning_bid.bid_id,
            agreed_price=result.final_price,
            status=ExecutionStatus.ASSIGNED,
            deadline=task.deadline,
        )

        return result, execution

    def update_bid_statuses(
        self,
        bids: list[Bid],
        winner_bid_id: str | None,
    ) -> list[Bid]:
        """Update bid statuses after auction."""
        now = datetime.utcnow()
        for bid in bids:
            if bid.bid_id == winner_bid_id:
                bid.status = BidStatus.ACCEPTED
            else:
                bid.status = BidStatus.REJECTED
            bid.resolved_at = now
        return bids

    def update_task_after_allocation(
        self,
        task: Task,
        result: AuctionResult,
    ) -> Task:
        """Update task after allocation."""
        if result.has_winner:
            task.status = TaskStatus.ASSIGNED
            task.assigned_at = datetime.utcnow()
            task.assigned_agent_id = result.winner_id
            task.winning_bid_id = result.winning_bid.bid_id
            task.final_price = result.final_price
        else:
            # No winner - mark as expired or keep open based on policy
            task.status = TaskStatus.EXPIRED
        return task
