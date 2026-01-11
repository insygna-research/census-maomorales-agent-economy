"""Agent data models."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AutonomyLevel(str, Enum):
    """Level of autonomy for an agent."""

    FULL = "full"  # No human needed
    SUPERVISED = "supervised"  # Human reviews output
    HUMAN_REQUIRED = "human_required"  # Human does core work
    HYBRID = "hybrid"  # Mix depending on task


class PricingStrategy(str, Enum):
    """Pricing strategy for an agent."""

    FIXED = "fixed"  # Fixed price per task type
    HOURLY = "hourly"  # Price per hour of work
    DYNAMIC = "dynamic"  # Adjusts based on demand/reputation
    COST_PLUS = "cost_plus"  # Cost plus margin


class Capability(BaseModel):
    """A capability that an agent can perform."""

    name: str = Field(..., description="Capability identifier, e.g., 'code_review'")
    skill_level: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Self-reported skill level"
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict, description="Capability-specific constraints"
    )

    def __hash__(self) -> int:
        return hash(self.name)


class AvailabilitySchedule(BaseModel):
    """Agent availability schedule."""

    available_now: bool = Field(default=True, description="Is agent currently available?")
    max_concurrent_tasks: int = Field(default=1, description="Max tasks at once")
    current_task_count: int = Field(default=0, description="Current active tasks")
    estimated_free_at: datetime | None = Field(
        default=None, description="When agent will be free"
    )
    timezone: str = Field(default="UTC", description="Agent's timezone")
    # For human agents
    typical_response_time: timedelta | None = Field(
        default=None, description="Expected response latency"
    )

    @property
    def has_capacity(self) -> bool:
        """Check if agent has capacity for more tasks."""
        return self.available_now and self.current_task_count < self.max_concurrent_tasks


class PricingModel(BaseModel):
    """Agent's pricing model."""

    strategy: PricingStrategy = Field(default=PricingStrategy.FIXED)
    base_rate: float = Field(default=1.0, ge=0, description="Base rate in credits")
    min_price: float = Field(default=0.1, ge=0, description="Minimum acceptable price")
    max_price: float | None = Field(default=None, description="Maximum price cap")
    # For dynamic pricing
    demand_multiplier: float = Field(default=1.0, ge=0.1, le=10.0)
    # Capability-specific pricing
    capability_rates: dict[str, float] = Field(
        default_factory=dict, description="Rate overrides per capability"
    )

    def get_rate(self, capability: str | None = None) -> float:
        """Get the rate for a specific capability."""
        if capability and capability in self.capability_rates:
            return self.capability_rates[capability]
        return self.base_rate * self.demand_multiplier


class AgentProfile(BaseModel):
    """Complete agent profile."""

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(default="", description="Agent description")
    capabilities: list[Capability] = Field(
        default_factory=list, description="List of agent capabilities"
    )
    availability: AvailabilitySchedule = Field(
        default_factory=AvailabilitySchedule, description="Availability schedule"
    )
    pricing: PricingModel = Field(
        default_factory=PricingModel, description="Pricing model"
    )
    autonomy_level: AutonomyLevel = Field(
        default=AutonomyLevel.FULL, description="Level of autonomy"
    )
    human_latency: timedelta | None = Field(
        default=None, description="Expected response time for human-backed agents"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    registered_at: datetime = Field(
        default_factory=datetime.utcnow, description="Registration timestamp"
    )
    last_seen: datetime = Field(
        default_factory=datetime.utcnow, description="Last heartbeat timestamp"
    )

    def has_capability(self, name: str) -> bool:
        """Check if agent has a specific capability."""
        return any(c.name == name for c in self.capabilities)

    def get_capability(self, name: str) -> Capability | None:
        """Get a specific capability by name."""
        for c in self.capabilities:
            if c.name == name:
                return c
        return None

    @property
    def capability_names(self) -> list[str]:
        """Get list of capability names."""
        return [c.name for c in self.capabilities]

    @property
    def is_human_backed(self) -> bool:
        """Check if agent requires human involvement."""
        return self.autonomy_level in (AutonomyLevel.HUMAN_REQUIRED, AutonomyLevel.SUPERVISED)
