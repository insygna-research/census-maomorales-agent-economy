"""Auction mechanisms for task allocation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from economy.models import AllocationMethod, Bid, Task


@dataclass
class AuctionResult:
    """Result of an auction."""

    task_id: str
    winner_id: str | None
    winning_bid: Bid | None
    final_price: float
    all_bids: list[Bid]
    mechanism_used: AllocationMethod
    metadata: dict[str, Any]

    @property
    def has_winner(self) -> bool:
        """Check if auction has a winner."""
        return self.winner_id is not None


class AuctionEngine:
    """
    Engine for running different types of auctions.

    Supports:
    - Fixed price (first acceptable bid wins)
    - First-price auction (lowest bid wins, pays bid)
    - Second-price auction (lowest bid wins, pays second-lowest)
    - Reputation-weighted (score = f(bid, reputation))
    """

    def __init__(
        self,
        reputation_weight: float = 0.3,
        min_bids_for_auction: int = 1,
    ) -> None:
        """
        Initialize auction engine.

        Args:
            reputation_weight: Weight for reputation in weighted auctions (0-1)
            min_bids_for_auction: Minimum bids required to run auction
        """
        self.reputation_weight = reputation_weight
        self.min_bids_for_auction = min_bids_for_auction

    def run_auction(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float] | None = None,
    ) -> AuctionResult:
        """
        Run an auction for a task.

        Args:
            task: The task being auctioned
            bids: List of submitted bids
            reputation_scores: Optional dict of agent_id -> reputation score (0-1)

        Returns:
            AuctionResult with winner information
        """
        if not bids:
            return AuctionResult(
                task_id=task.task_id,
                winner_id=None,
                winning_bid=None,
                final_price=0,
                all_bids=[],
                mechanism_used=task.allocation_method,
                metadata={"reason": "no_bids"},
            )

        reputation_scores = reputation_scores or {}

        match task.allocation_method:
            case AllocationMethod.FIXED_PRICE:
                return self._fixed_price_allocation(task, bids)
            case AllocationMethod.FIRST_PRICE_AUCTION:
                return self._first_price_auction(task, bids)
            case AllocationMethod.SECOND_PRICE_AUCTION:
                return self._second_price_auction(task, bids)
            case AllocationMethod.REPUTATION_WEIGHTED:
                return self._reputation_weighted_auction(task, bids, reputation_scores)
            case _:
                # Default to first-price
                return self._first_price_auction(task, bids)

    def _fixed_price_allocation(self, task: Task, bids: list[Bid]) -> AuctionResult:
        """
        Fixed price: first bid at or below max price wins.

        In real-time, this would be "first come, first served".
        In batch mode, we pick the earliest bid.
        """
        # Sort by submission time
        sorted_bids = sorted(bids, key=lambda b: b.submitted_at)

        for bid in sorted_bids:
            if bid.price <= task.budget.max_price:
                return AuctionResult(
                    task_id=task.task_id,
                    winner_id=bid.agent_id,
                    winning_bid=bid,
                    final_price=bid.price,
                    all_bids=bids,
                    mechanism_used=AllocationMethod.FIXED_PRICE,
                    metadata={"selection": "first_acceptable"},
                )

        return AuctionResult(
            task_id=task.task_id,
            winner_id=None,
            winning_bid=None,
            final_price=0,
            all_bids=bids,
            mechanism_used=AllocationMethod.FIXED_PRICE,
            metadata={"reason": "no_acceptable_bids"},
        )

    def _first_price_auction(self, task: Task, bids: list[Bid]) -> AuctionResult:
        """
        First-price auction: lowest bid wins and pays their bid.

        This is the standard competitive bidding mechanism.
        """
        # Filter valid bids
        valid_bids = [b for b in bids if b.price <= task.budget.max_price]

        if not valid_bids:
            return AuctionResult(
                task_id=task.task_id,
                winner_id=None,
                winning_bid=None,
                final_price=0,
                all_bids=bids,
                mechanism_used=AllocationMethod.FIRST_PRICE_AUCTION,
                metadata={"reason": "no_valid_bids"},
            )

        # Sort by price (lowest first), then by time (earliest first for ties)
        sorted_bids = sorted(valid_bids, key=lambda b: (b.price, b.submitted_at))
        winner = sorted_bids[0]

        return AuctionResult(
            task_id=task.task_id,
            winner_id=winner.agent_id,
            winning_bid=winner,
            final_price=winner.price,
            all_bids=bids,
            mechanism_used=AllocationMethod.FIRST_PRICE_AUCTION,
            metadata={
                "num_bids": len(bids),
                "num_valid_bids": len(valid_bids),
                "price_range": (
                    min(b.price for b in valid_bids),
                    max(b.price for b in valid_bids),
                ),
            },
        )

    def _second_price_auction(self, task: Task, bids: list[Bid]) -> AuctionResult:
        """
        Second-price (Vickrey) auction: lowest bid wins, pays second-lowest.

        This encourages truthful bidding since overbidding doesn't help
        and underbidding risks losing.
        """
        valid_bids = [b for b in bids if b.price <= task.budget.max_price]

        if not valid_bids:
            return AuctionResult(
                task_id=task.task_id,
                winner_id=None,
                winning_bid=None,
                final_price=0,
                all_bids=bids,
                mechanism_used=AllocationMethod.SECOND_PRICE_AUCTION,
                metadata={"reason": "no_valid_bids"},
            )

        sorted_bids = sorted(valid_bids, key=lambda b: (b.price, b.submitted_at))
        winner = sorted_bids[0]

        # Second price: if only one bid, pay the bid; otherwise pay second-lowest
        if len(sorted_bids) >= 2:
            second_price = sorted_bids[1].price
        else:
            # Only one bid - they pay their bid (or could use max budget)
            second_price = winner.price

        return AuctionResult(
            task_id=task.task_id,
            winner_id=winner.agent_id,
            winning_bid=winner,
            final_price=second_price,
            all_bids=bids,
            mechanism_used=AllocationMethod.SECOND_PRICE_AUCTION,
            metadata={
                "num_bids": len(bids),
                "winning_bid_price": winner.price,
                "second_price": second_price,
                "savings": second_price - winner.price,
            },
        )

    def _reputation_weighted_auction(
        self,
        task: Task,
        bids: list[Bid],
        reputation_scores: dict[str, float],
    ) -> AuctionResult:
        """
        Reputation-weighted auction: score = (1-w)*price_score + w*reputation.

        Lower price and higher reputation both contribute to winning.
        This helps prevent a race to the bottom on price.
        """
        valid_bids = [b for b in bids if b.price <= task.budget.max_price]

        if not valid_bids:
            return AuctionResult(
                task_id=task.task_id,
                winner_id=None,
                winning_bid=None,
                final_price=0,
                all_bids=bids,
                mechanism_used=AllocationMethod.REPUTATION_WEIGHTED,
                metadata={"reason": "no_valid_bids"},
            )

        # Normalize prices (lower is better -> higher normalized score)
        min_price = min(b.price for b in valid_bids)
        max_price = max(b.price for b in valid_bids)
        price_range = max_price - min_price if max_price > min_price else 1.0

        def compute_score(bid: Bid) -> float:
            # Price score: 1.0 for lowest price, 0.0 for highest
            price_score = 1.0 - (bid.price - min_price) / price_range

            # Reputation score (default 0.5 for unknown agents)
            rep_score = reputation_scores.get(bid.agent_id, 0.5)

            # Weighted combination
            w = self.reputation_weight
            return (1 - w) * price_score + w * rep_score

        # Score all bids
        scored_bids = [(bid, compute_score(bid)) for bid in valid_bids]
        scored_bids.sort(key=lambda x: (-x[1], x[0].submitted_at))  # Highest score first

        winner, winner_score = scored_bids[0]

        return AuctionResult(
            task_id=task.task_id,
            winner_id=winner.agent_id,
            winning_bid=winner,
            final_price=winner.price,
            all_bids=bids,
            mechanism_used=AllocationMethod.REPUTATION_WEIGHTED,
            metadata={
                "num_bids": len(bids),
                "winner_score": winner_score,
                "winner_reputation": reputation_scores.get(winner.agent_id, 0.5),
                "reputation_weight": self.reputation_weight,
                "all_scores": {b.agent_id: s for b, s in scored_bids},
            },
        )


class AuctionScheduler:
    """Scheduler for running auctions at the right time."""

    def __init__(self, engine: AuctionEngine) -> None:
        self.engine = engine
        self._pending_auctions: dict[str, datetime] = {}

    def schedule_auction(self, task: Task) -> None:
        """Schedule an auction to run when task's auction period ends."""
        if task.auction_ends_at:
            self._pending_auctions[task.task_id] = task.auction_ends_at

    def get_due_auctions(self, now: datetime | None = None) -> list[str]:
        """Get task IDs for auctions that are due."""
        now = now or datetime.utcnow()
        due = [
            task_id
            for task_id, end_time in self._pending_auctions.items()
            if now >= end_time
        ]
        return due

    def complete_auction(self, task_id: str) -> None:
        """Mark an auction as complete."""
        self._pending_auctions.pop(task_id, None)
