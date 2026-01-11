"""Trust and reputation dynamics experiment.

Research Question: How fragile is trust and reputation?
"""

from experiments.runner import ExperimentConfig
from experiments.synthetic_agents import SyntheticAgentConfig, create_diverse_agents
from economy.models import AllocationMethod


def create_mixed_reliability_agents(
    total: int = 20,
    unreliable_fraction: float = 0.2,
) -> list[SyntheticAgentConfig]:
    """Create a mix of reliable and unreliable agents."""
    agents = []
    num_unreliable = int(total * unreliable_fraction)

    # Reliable agents
    for i in range(total - num_unreliable):
        agents.append(SyntheticAgentConfig(
            name=f"Reliable_{i}",
            capabilities=["general", "coding", "writing"],
            success_rate=0.9 + 0.09 * (i % 2),  # 90-99% reliable
            quality_mean=0.8,
            quality_std=0.1,
            bid_aggressiveness=0.5 + 0.2 * (i % 3) / 2,
        ))

    # Unreliable/bad actors
    for i in range(num_unreliable):
        agents.append(SyntheticAgentConfig(
            name=f"Unreliable_{i}",
            capabilities=["general", "coding", "writing"],
            success_rate=0.3 + 0.2 * (i % 3),  # 30-50% reliable
            quality_mean=0.4,
            quality_std=0.3,  # High variance
            bid_aggressiveness=0.9,  # Very cheap to attract tasks
        ))

    return agents


def create_trust_dynamics_configs() -> list[ExperimentConfig]:
    """Create configs for different bad actor scenarios."""
    configs = []

    # Baseline: No bad actors
    configs.append(ExperimentConfig(
        name="trust_baseline_0pct",
        description="Baseline with 0% unreliable agents",
        duration_seconds=300,
        agent_configs=create_mixed_reliability_agents(20, 0.0),
        task_types=["simple", "coding"],
        tasks_per_minute=4.0,
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=30,
    ))

    # 10% bad actors
    configs.append(ExperimentConfig(
        name="trust_10pct_unreliable",
        description="10% unreliable agents",
        duration_seconds=300,
        agent_configs=create_mixed_reliability_agents(20, 0.1),
        task_types=["simple", "coding"],
        tasks_per_minute=4.0,
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=30,
    ))

    # 30% bad actors
    configs.append(ExperimentConfig(
        name="trust_30pct_unreliable",
        description="30% unreliable agents",
        duration_seconds=300,
        agent_configs=create_mixed_reliability_agents(20, 0.3),
        task_types=["simple", "coding"],
        tasks_per_minute=4.0,
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=30,
    ))

    # 50% bad actors
    configs.append(ExperimentConfig(
        name="trust_50pct_unreliable",
        description="50% unreliable agents",
        duration_seconds=300,
        agent_configs=create_mixed_reliability_agents(20, 0.5),
        task_types=["simple", "coding"],
        tasks_per_minute=4.0,
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=30,
    ))

    return configs


class TrustDynamicsExperiment:
    """
    Experiment to study trust and reputation dynamics.

    Hypothesis: The reputation system should identify and penalize
    unreliable agents over time, but high proportions of bad actors
    may overwhelm the system before reputations stabilize.

    What to measure:
    - Time to identify bad actors (reputation < 0.5)
    - Market efficiency degradation vs baseline
    - Recovery time after bad actor tasks fail
    - False positive rate (good agents penalized)
    - Correlation between success rate and reputation

    Key questions:
    - At what % of bad actors does the market break down?
    - How quickly can reputation identify bad actors?
    - Does cheap pricing help bad actors get tasks despite low reputation?
    """

    @staticmethod
    def get_configs() -> list[ExperimentConfig]:
        return create_trust_dynamics_configs()

    @staticmethod
    async def run_all(server_url: str = "http://localhost:8000"):
        """Run all trust dynamics experiments."""
        from experiments.runner import ExperimentRunner

        results = []
        for config in create_trust_dynamics_configs():
            config.server_url = server_url
            runner = ExperimentRunner(config)
            result = await runner.run()
            results.append(result)

        return results
