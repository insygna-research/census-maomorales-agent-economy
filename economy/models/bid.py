"""Bid data models."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BidStatus(str, Enum):
    """Bid status."""

    PENDING = "pending"  # Awaiting auction result
    ACCEPTED = "accepted"  # Bid won
    REJECTED = "rejected"  # Bid lost
    WITHDRAWN = "withdrawn"  # Agent withdrew bid
    EXPIRED = "expired"  # Auction closed without selection


class Bid(BaseModel):
    """An agent's bid on a task."""

    bid_id: str = Field(..., description="Unique bid identifier")
    task_id: str = Field(..., description="Task being bid on")
    agent_id: str = Field(..., description="Agent making the bid")
    price: float = Field(..., gt=0, description="Bid price in credits")
    estimated_duration: timedelta = Field(
        default=timedelta(hours=1), description="Estimated time to complete"
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence in estimate"
    )
    proposed_approach: str | None = Field(
        default=None, description="Brief description of approach"
    )
    status: BidStatus = Field(default=BidStatus.PENDING, description="Bid status")
    submitted_at: datetime = Field(
        default_factory=datetime.utcnow, description="Submission timestamp"
    )
    resolved_at: datetime | None = Field(
        default=None, description="When bid was accepted/rejected"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def is_pending(self) -> bool:
        """Check if bid is still pending."""
        return self.status == BidStatus.PENDING

    @property
    def is_won(self) -> bool:
        """Check if bid was accepted."""
        return self.status == BidStatus.ACCEPTED
