"""Execution data models."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Execution lifecycle status."""

    ASSIGNED = "assigned"  # Task assigned, not started
    IN_PROGRESS = "in_progress"  # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Execution failed
    TIMEOUT = "timeout"  # Exceeded deadline
    CANCELLED = "cancelled"  # Cancelled by agent or publisher


class ExecutionResult(BaseModel):
    """Result of task execution."""

    output: Any = Field(..., description="Primary output")
    output_type: str = Field(default="text", description="Type of output")
    artifacts: list[str] = Field(
        default_factory=list, description="Paths/URLs to artifacts"
    )
    execution_log: list[str] = Field(
        default_factory=list, description="Execution log entries"
    )
    actual_duration: timedelta = Field(..., description="Actual time taken")
    tokens_used: int | None = Field(
        default=None, description="LLM tokens used if applicable"
    )
    cost_incurred: float | None = Field(
        default=None, description="Actual cost incurred by agent"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional result metadata"
    )


class Evaluation(BaseModel):
    """Evaluation of an execution."""

    evaluation_id: str = Field(..., description="Unique evaluation identifier")
    execution_id: str = Field(..., description="Execution being evaluated")
    evaluator_id: str = Field(..., description="Who performed evaluation")
    evaluator_type: str = Field(
        default="automated", description="Type: automated, llm, human"
    )
    criterion_scores: dict[str, float] = Field(
        default_factory=dict, description="Score per criterion (0-1)"
    )
    overall_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall quality score"
    )
    feedback: str = Field(default="", description="Textual feedback")
    passed: bool = Field(default=True, description="Whether execution passed")
    evaluated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Evaluation timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class Execution(BaseModel):
    """Record of a task execution."""

    execution_id: str = Field(..., description="Unique execution identifier")
    task_id: str = Field(..., description="Task being executed")
    agent_id: str = Field(..., description="Agent executing the task")
    bid_id: str = Field(..., description="Winning bid ID")
    agreed_price: float = Field(..., description="Price agreed upon")
    status: ExecutionStatus = Field(
        default=ExecutionStatus.ASSIGNED, description="Current status"
    )
    started_at: datetime | None = Field(
        default=None, description="When execution started"
    )
    completed_at: datetime | None = Field(
        default=None, description="When execution completed"
    )
    deadline: datetime | None = Field(default=None, description="Execution deadline")
    result: ExecutionResult | None = Field(default=None, description="Execution result")
    evaluation: Evaluation | None = Field(
        default=None, description="Post-execution evaluation"
    )
    failure_reason: str | None = Field(
        default=None, description="Reason for failure if failed"
    )
    retry_count: int = Field(default=0, description="Number of retries")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def is_active(self) -> bool:
        """Check if execution is still active."""
        return self.status in (ExecutionStatus.ASSIGNED, ExecutionStatus.IN_PROGRESS)

    @property
    def is_complete(self) -> bool:
        """Check if execution is finished (success or failure)."""
        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED,
        )

    @property
    def is_success(self) -> bool:
        """Check if execution completed successfully."""
        return self.status == ExecutionStatus.COMPLETED

    @property
    def duration(self) -> timedelta | None:
        """Get execution duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
