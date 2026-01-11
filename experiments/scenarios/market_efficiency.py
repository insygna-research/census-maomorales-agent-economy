"""Market efficiency experiment.

Research Question: Can market mechanisms outperform static agent orchestration?
"""

from experiments.runner import ExperimentConfig
from experiments.synthetic_agents import create_diverse_agents, SyntheticAgentConfig
from economy.models import AllocationMethod


def create_market_efficiency_configs() -> list[ExperimentConfig]:
    """Create configs to compare different allocation methods."""
    base_agents = create_diverse_agents(10)

    configs = []

    # Baseline: Random allocation (simulated by very short auction)
    configs.append(ExperimentConfig(
        name="random_allocation",
        description="Random allocation baseline - first bid wins",
        duration_seconds=300,
        agent_configs=base_agents,
        task_types=["simple", "coding"],
        tasks_per_minute=3.0,
        allocation_method=AllocationMethod.FIXED_PRICE,
        auction_duration_seconds=60,  # 1 minute minimum
    ))

    # First-price auction
    configs.append(ExperimentConfig(
        name="first_price_auction",
        description="First-price sealed-bid auction",
        duration_seconds=300,
        agent_configs=base_agents,
        task_types=["simple", "coding"],
        tasks_per_minute=3.0,
        allocation_method=AllocationMethod.FIRST_PRICE_AUCTION,
        auction_duration_seconds=30,
    ))

    # Second-price auction
    configs.append(ExperimentConfig(
        name="second_price_auction",
        description="Second-price (Vickrey) auction",
        duration_seconds=300,
        agent_configs=base_agents,
        task_types=["simple", "coding"],
        tasks_per_minute=3.0,
        allocation_method=AllocationMethod.SECOND_PRICE_AUCTION,
        auction_duration_seconds=30,
    ))

    # Reputation-weighted auction
    configs.append(ExperimentConfig(
        name="reputation_weighted",
        description="Reputation-weighted auction",
        duration_seconds=300,
        agent_configs=base_agents,
        task_types=["simple", "coding"],
        tasks_per_minute=3.0,
        allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
        auction_duration_seconds=30,
    ))

    return configs


class MarketEfficiencyExperiment:
    """
    Experiment comparing market allocation mechanisms.

    Hypothesis: Market mechanisms (especially reputation-weighted) will
    achieve higher quality outcomes than random allocation, but may have
    higher costs.

    Metrics to compare:
    - Completion rate
    - Average quality score
    - Average price paid
    - Time to allocation
    - Agent utilization
    """

    @staticmethod
    def get_configs() -> list[ExperimentConfig]:
        return create_market_efficiency_configs()

    @staticmethod
    async def run_all(server_url: str = "http://localhost:8000"):
        """Run all market efficiency experiments."""
        from experiments.runner import ExperimentRunner

        results = []
        for config in create_market_efficiency_configs():
            config.server_url = server_url
            runner = ExperimentRunner(config)
            result = await runner.run()
            results.append(result)

        return results
