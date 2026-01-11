"""Synthetic agents for experiments."""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from rich.console import Console

from economy.models import ExecutionResult, Task
from economy.agents.base import BaseAgent

console = Console()


@dataclass
class SyntheticAgentConfig:
    """Configuration for a synthetic agent."""

    name: str
    capabilities: list[str] = field(default_factory=lambda: ["general"])

    # Performance characteristics
    success_rate: float = 0.9  # Probability of successful execution
    quality_mean: float = 0.8  # Mean quality score
    quality_std: float = 0.1  # Standard deviation of quality
    execution_time_mean: float = 5.0  # Mean execution time in seconds
    execution_time_std: float = 2.0  # Std dev of execution time

    # Bidding behavior
    bid_probability: float = 0.8  # Probability of bidding on matching tasks
    bid_aggressiveness: float = 0.7  # How aggressively to bid (0=max budget, 1=min)
    bid_noise: float = 0.1  # Random noise in bid price

    # Reliability
    availability: float = 1.0  # Probability of being available
    latency_mean: float = 0.5  # Mean response latency in seconds

    # Strategy
    specialization: float = 0.5  # How specialized vs generalist (affects capability matching)


class SyntheticAgent(BaseAgent):
    """
    Synthetic agent for experiments.

    Simulates realistic agent behavior with configurable characteristics.
    """

    def __init__(
        self,
        config: SyntheticAgentConfig,
        server_url: str = "http://localhost:8000",
    ) -> None:
        super().__init__(
            name=config.name,
            capabilities=config.capabilities,
            server_url=server_url,
            description=f"Synthetic agent: {config.name}",
            base_rate=1.0,
            autonomy_level="full",
        )
        self.config = config

        # Stats tracking
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_earned = 0.0
        self.bids_submitted = 0

    async def should_bid(self, task: Task) -> bool:
        """Decide whether to bid based on configuration."""
        # Check availability
        if random.random() > self.config.availability:
            return False

        # Check capability match
        required = set(task.specification.required_capabilities)
        mine = set(self.capabilities)

        if required:
            overlap = len(required & mine) / len(required)
            # More specialized agents are pickier
            threshold = self.config.specialization * 0.5
            if overlap < threshold:
                return False

        # Random bid decision
        return random.random() < self.config.bid_probability

    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """Compute bid with configured behavior."""
        # Simulate latency
        await asyncio.sleep(random.gauss(
            self.config.latency_mean,
            self.config.latency_mean * 0.2,
        ))

        # Calculate base price
        budget_range = task.budget.max_price - task.budget.min_price
        base = task.budget.min_price + budget_range * (1 - self.config.bid_aggressiveness)

        # Add noise
        noise = random.gauss(0, self.config.bid_noise * budget_range)
        price = max(task.budget.min_price, min(task.budget.max_price, base + noise))

        # Estimate time based on config
        estimated_minutes = max(1, int(self.config.execution_time_mean / 60 * 2))

        self.bids_submitted += 1

        return {
            "price": price,
            "estimated_minutes": estimated_minutes,
            "confidence": random.uniform(0.6, 0.95),
            "approach": f"Synthetic execution by {self.name}",
        }

    async def execute(self, task: Task) -> ExecutionResult:
        """Execute task with simulated characteristics."""
        # Simulate execution time
        exec_time = max(
            0.5,
            random.gauss(
                self.config.execution_time_mean,
                self.config.execution_time_std,
            ),
        )
        await asyncio.sleep(exec_time)

        # Determine success
        success = random.random() < self.config.success_rate

        if not success:
            self.tasks_failed += 1
            raise Exception(f"Synthetic failure for {self.name}")

        # Generate quality score
        quality = max(0, min(1, random.gauss(
            self.config.quality_mean,
            self.config.quality_std,
        )))

        self.tasks_completed += 1

        return ExecutionResult(
            output=f"Synthetic output from {self.name} for task: {task.specification.title}",
            output_type="text",
            execution_log=[
                f"Synthetic agent {self.name} started",
                f"Execution time: {exec_time:.1f}s",
                f"Quality score: {quality:.2f}",
            ],
            actual_duration=timedelta(seconds=exec_time),
            metadata={
                "synthetic": True,
                "quality_score": quality,
            },
        )


# Predefined agent configurations for common scenarios
RELIABLE_AGENT = SyntheticAgentConfig(
    name="ReliableBot",
    capabilities=["general", "coding", "writing"],
    success_rate=0.95,
    quality_mean=0.85,
    bid_aggressiveness=0.5,
)

CHEAP_AGENT = SyntheticAgentConfig(
    name="BudgetBot",
    capabilities=["general"],
    success_rate=0.75,
    quality_mean=0.6,
    bid_aggressiveness=0.9,  # Very aggressive bidding
)

SPECIALIST_AGENT = SyntheticAgentConfig(
    name="SpecialistBot",
    capabilities=["coding"],
    success_rate=0.9,
    quality_mean=0.95,
    quality_std=0.05,
    bid_aggressiveness=0.3,  # Premium pricing
    specialization=0.9,
)

UNRELIABLE_AGENT = SyntheticAgentConfig(
    name="UnreliableBot",
    capabilities=["general", "coding", "writing"],
    success_rate=0.5,  # Fails often
    quality_mean=0.7,
    quality_std=0.3,  # High variance
    bid_aggressiveness=0.8,  # Cheap
)

SLOW_AGENT = SyntheticAgentConfig(
    name="SlowBot",
    capabilities=["research", "analysis"],
    success_rate=0.9,
    quality_mean=0.9,
    execution_time_mean=20.0,  # Slow but thorough
    latency_mean=2.0,
)


def create_diverse_agents(n: int = 10) -> list[SyntheticAgentConfig]:
    """Create a diverse set of synthetic agents."""
    agents = []

    # Mix of agent types
    for i in range(n):
        if i % 5 == 0:
            config = SyntheticAgentConfig(
                name=f"Reliable_{i}",
                capabilities=["general", "coding", "writing"],
                success_rate=random.uniform(0.85, 0.99),
                quality_mean=random.uniform(0.75, 0.95),
                bid_aggressiveness=random.uniform(0.4, 0.7),
            )
        elif i % 5 == 1:
            config = SyntheticAgentConfig(
                name=f"Budget_{i}",
                capabilities=["general"],
                success_rate=random.uniform(0.6, 0.8),
                quality_mean=random.uniform(0.5, 0.7),
                bid_aggressiveness=random.uniform(0.8, 0.95),
            )
        elif i % 5 == 2:
            cap = random.choice(["coding", "writing", "research", "analysis"])
            config = SyntheticAgentConfig(
                name=f"Specialist_{cap}_{i}",
                capabilities=[cap],
                success_rate=random.uniform(0.85, 0.95),
                quality_mean=random.uniform(0.85, 0.98),
                bid_aggressiveness=random.uniform(0.2, 0.5),
                specialization=random.uniform(0.7, 0.95),
            )
        elif i % 5 == 3:
            config = SyntheticAgentConfig(
                name=f"Risky_{i}",
                capabilities=["general", "coding"],
                success_rate=random.uniform(0.4, 0.7),
                quality_mean=random.uniform(0.6, 0.8),
                quality_std=random.uniform(0.15, 0.3),
                bid_aggressiveness=random.uniform(0.7, 0.9),
            )
        else:
            config = SyntheticAgentConfig(
                name=f"Balanced_{i}",
                capabilities=["general", "writing", "research"],
                success_rate=random.uniform(0.75, 0.9),
                quality_mean=random.uniform(0.7, 0.85),
                bid_aggressiveness=random.uniform(0.5, 0.7),
            )

        agents.append(config)

    return agents
