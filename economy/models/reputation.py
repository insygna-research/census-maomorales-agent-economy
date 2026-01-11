"""Reputation data models."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class PerformanceRecord(BaseModel):
    """Record of an agent's performance on a single task."""

    record_id: str = Field(..., description="Unique record identifier")
    agent_id: str = Field(..., description="Agent identifier")
    task_id: str = Field(..., description="Task identifier")
    execution_id: str = Field(..., description="Execution identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this record was created"
    )

    # Completion metrics
    completed: bool = Field(..., description="Was task completed?")
    on_time: bool = Field(default=True, description="Was it completed on time?")

    # Time metrics
    estimated_duration: timedelta = Field(..., description="Estimated duration from bid")
    actual_duration: timedelta | None = Field(
        default=None, description="Actual duration"
    )

    # Quality metrics
    quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Quality score from evaluation"
    )

    # Economic metrics
    bid_price: float = Field(..., description="Original bid price")
    final_price: float = Field(..., description="Final price paid")
    publisher_satisfaction: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Publisher satisfaction rating"
    )

    # Task context
    task_type: str = Field(default="unknown", description="Type of task")
    required_capabilities: list[str] = Field(
        default_factory=list, description="Capabilities required"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def duration_accuracy(self) -> float | None:
        """How accurate was the duration estimate (1.0 = perfect)."""
        if self.actual_duration is None:
            return None
        estimated_seconds = self.estimated_duration.total_seconds()
        actual_seconds = self.actual_duration.total_seconds()
        if estimated_seconds == 0:
            return 0.0
        # Return ratio, capped at 2.0 for very inaccurate estimates
        ratio = actual_seconds / estimated_seconds
        if ratio > 2.0:
            return 0.0
        if ratio < 0.5:
            return 0.5  # Underestimate is less bad
        return 1.0 - abs(1.0 - ratio)


class ReputationSummary(BaseModel):
    """Aggregated reputation summary for an agent."""

    agent_id: str = Field(..., description="Agent identifier")
    computed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this was computed"
    )

    # Core reputation score
    overall_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Overall reputation score"
    )

    # Component scores
    completion_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Task completion rate"
    )
    on_time_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="On-time delivery rate"
    )
    average_quality: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Average quality score"
    )
    duration_accuracy: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Estimation accuracy"
    )
    average_satisfaction: float | None = Field(
        default=None, description="Average publisher satisfaction"
    )

    # Volume metrics
    total_tasks: int = Field(default=0, description="Total tasks attempted")
    completed_tasks: int = Field(default=0, description="Tasks completed")
    failed_tasks: int = Field(default=0, description="Tasks failed")

    # Economic metrics
    total_earnings: float = Field(default=0.0, description="Total earnings")
    average_price: float = Field(default=0.0, description="Average task price")

    # Capability-specific scores
    capability_scores: dict[str, float] = Field(
        default_factory=dict, description="Reputation per capability"
    )

    # Trust signals
    age_days: int = Field(default=0, description="Days since first task")
    recent_activity: int = Field(
        default=0, description="Tasks in last 7 days"
    )

    # Confidence in score
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence in reputation score (increases with more data)"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def is_reliable(self) -> bool:
        """Quick check if agent is considered reliable."""
        return (
            self.overall_score >= 0.6
            and self.completion_rate >= 0.8
            and self.total_tasks >= 3
        )

    @property
    def tier(self) -> str:
        """Get agent tier based on reputation."""
        if self.total_tasks < 3:
            return "newcomer"
        if self.overall_score >= 0.9:
            return "elite"
        if self.overall_score >= 0.75:
            return "trusted"
        if self.overall_score >= 0.5:
            return "standard"
        return "risky"


class ReputationEvent(BaseModel):
    """An event that affects reputation."""

    event_id: str = Field(..., description="Unique event identifier")
    agent_id: str = Field(..., description="Agent identifier")
    event_type: str = Field(..., description="Type of event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    impact: float = Field(
        default=0.0, description="Impact on reputation (-1 to 1)"
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Event details"
    )
