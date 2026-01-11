"""Task data models."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task lifecycle status."""

    DRAFT = "draft"  # Not yet published
    OPEN = "open"  # Accepting bids
    AUCTION_CLOSED = "auction_closed"  # Bidding ended, winner being selected
    ASSIGNED = "assigned"  # Winner selected, awaiting execution
    IN_PROGRESS = "in_progress"  # Being executed
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Cancelled by publisher
    EXPIRED = "expired"  # Deadline passed without completion


class AllocationMethod(str, Enum):
    """How tasks are allocated to agents."""

    FIXED_PRICE = "fixed_price"  # First agent to accept wins
    FIRST_PRICE_AUCTION = "first_price"  # Lowest bid wins, pays bid
    SECOND_PRICE_AUCTION = "second_price"  # Lowest bid wins, pays second-lowest
    REPUTATION_WEIGHTED = "reputation_weighted"  # Score = f(bid, reputation)


class Budget(BaseModel):
    """Task budget specification."""

    min_price: float = Field(default=0.0, ge=0, description="Minimum acceptable price")
    max_price: float = Field(..., gt=0, description="Maximum budget")
    currency: str = Field(default="credits", description="Currency type")

    def is_acceptable(self, price: float) -> bool:
        """Check if a price is within budget."""
        return self.min_price <= price <= self.max_price


class EvaluationCriterion(BaseModel):
    """Criterion for evaluating task completion."""

    name: str = Field(..., description="Criterion name")
    description: str = Field(default="", description="What this criterion measures")
    weight: float = Field(default=1.0, ge=0, description="Weight in final score")
    evaluator_type: str = Field(
        default="manual", description="Type of evaluator: manual, llm, automated"
    )
    evaluator_config: dict[str, Any] = Field(
        default_factory=dict, description="Evaluator-specific configuration"
    )


class TaskSpec(BaseModel):
    """Task specification - what needs to be done."""

    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Detailed task description")
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required agent capabilities"
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Task inputs and context"
    )
    expected_output_format: str = Field(
        default="text", description="Expected output format"
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict, description="Task constraints"
    )
    examples: list[dict[str, Any]] = Field(
        default_factory=list, description="Example inputs/outputs"
    )


class Task(BaseModel):
    """A task in the marketplace."""

    task_id: str = Field(..., description="Unique task identifier")
    publisher_id: str = Field(..., description="ID of the agent/user who published")
    specification: TaskSpec = Field(..., description="Task specification")
    budget: Budget = Field(..., description="Budget for this task")
    deadline: datetime | None = Field(default=None, description="Task deadline")
    auction_duration: timedelta = Field(
        default=timedelta(minutes=5), description="How long to accept bids"
    )
    evaluation_criteria: list[EvaluationCriterion] = Field(
        default_factory=list, description="Evaluation criteria"
    )
    allocation_method: AllocationMethod = Field(
        default=AllocationMethod.FIRST_PRICE_AUCTION, description="Allocation method"
    )
    status: TaskStatus = Field(default=TaskStatus.DRAFT, description="Current status")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    published_at: datetime | None = Field(
        default=None, description="When task was published"
    )
    assigned_at: datetime | None = Field(
        default=None, description="When task was assigned"
    )
    completed_at: datetime | None = Field(
        default=None, description="When task was completed"
    )
    assigned_agent_id: str | None = Field(
        default=None, description="ID of assigned agent"
    )
    winning_bid_id: str | None = Field(
        default=None, description="ID of winning bid"
    )
    final_price: float | None = Field(
        default=None, description="Final price paid"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    parent_task_id: str | None = Field(
        default=None, description="Parent task if this is a subtask"
    )

    @property
    def is_open(self) -> bool:
        """Check if task is accepting bids."""
        return self.status == TaskStatus.OPEN

    @property
    def is_expired(self) -> bool:
        """Check if task deadline has passed."""
        if self.deadline is None:
            return False
        return datetime.utcnow() > self.deadline

    @property
    def auction_ends_at(self) -> datetime | None:
        """When the auction ends."""
        if self.published_at is None:
            return None
        return self.published_at + self.auction_duration
