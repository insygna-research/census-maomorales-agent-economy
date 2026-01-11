"""Specialization emergence experiment.

Research Question: Does specialization emerge naturally?
"""

from experiments.runner import ExperimentConfig
from experiments.synthetic_agents import SyntheticAgentConfig
from economy.models import AllocationMethod


def create_generalist_agents(n: int = 20) -> list[SyntheticAgentConfig]:
    """Create generalist agents that can adapt."""
    agents = []
    for i in range(n):
        agents.append(SyntheticAgentConfig(
            name=f"Generalist_{i}",
            # All agents start with all capabilities
            capabilities=["coding", "writing", "research", "analysis", "general"],
            success_rate=0.8,  # Moderate success
            quality_mean=0.7,  # Moderate quality
            quality_std=0.15,
            bid_aggressiveness=0.6,
            specialization=0.1,  # Low specialization initially
        ))
    return agents


def create_specialization_config(duration_minutes: int = 10) -> ExperimentConfig:
    """Create config for specialization experiment."""
    return ExperimentConfig(
        name="specialization_emergence",
        description="Test if agents naturally specialize over time",
        duration_seconds=duration_minutes * 60,
        agent_configs=create_generalist_agents(20),
        task_types=["simple", "coding", "research"],
        tasks_per_minute=5.0,  # High volume for learning
        task_budget_range=(2.0, 15.0),
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=20,
    )


class SpecializationExperiment:
    """
    Experiment to study emergent specialization.

    Hypothesis: When agents receive feedback (via reputation) and can
    adjust their bidding strategies, they will naturally specialize
    in tasks where they perform best.

    What to measure:
    - Per-agent task type distribution over time
    - Specialization index (entropy-based)
    - Quality improvement in specialized tasks
    - Price differentiation by task type

    Note: Full specialization testing requires agents that can learn
    and adapt their strategies. The current implementation uses static
    configs, so this experiment mainly tests the baseline behavior.
    Future work: Add adaptive bidding strategies.
    """

    @staticmethod
    def get_config(duration_minutes: int = 10) -> ExperimentConfig:
        return create_specialization_config(duration_minutes)

    @staticmethod
    async def run(
        duration_minutes: int = 10,
        server_url: str = "http://localhost:8000",
    ):
        """Run the specialization experiment."""
        from experiments.runner import ExperimentRunner

        config = create_specialization_config(duration_minutes)
        config.server_url = server_url

        runner = ExperimentRunner(config)
        return await runner.run()
