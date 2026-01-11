"""Experiment runner for agent economy research."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from economy.models import AllocationMethod
from economy.network.client import MarketClient
from experiments.synthetic_agents import SyntheticAgent, SyntheticAgentConfig
from experiments.metrics import MetricsCollector

console = Console()


@dataclass
class ExperimentConfig:
    """Configuration for an experiment."""

    name: str
    description: str = ""

    # Duration
    duration_seconds: int = 300  # 5 minutes default

    # Agent configuration
    agent_configs: list[SyntheticAgentConfig] = field(default_factory=list)

    # Task generation
    task_types: list[str] = field(default_factory=lambda: ["simple"])
    tasks_per_minute: float = 2.0
    task_budget_range: tuple[float, float] = (1.0, 10.0)

    # Market configuration
    allocation_method: AllocationMethod = AllocationMethod.FIRST_PRICE_AUCTION
    auction_duration_seconds: int = 30

    # Server
    server_url: str = "http://localhost:8000"

    # Output
    output_dir: str = "experiment_results"


@dataclass
class ExperimentResults:
    """Results from an experiment run."""

    config: ExperimentConfig
    start_time: datetime
    end_time: datetime
    duration: timedelta

    # Metrics
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_bids: int = 0
    total_transacted: float = 0.0

    # Agent metrics
    agent_stats: dict[str, dict] = field(default_factory=dict)

    # Time series data
    time_series: list[dict] = field(default_factory=list)

    # Raw events
    events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "config": {
                "name": self.config.name,
                "description": self.config.description,
                "duration_seconds": self.config.duration_seconds,
                "agent_count": len(self.config.agent_configs),
                "tasks_per_minute": self.config.tasks_per_minute,
                "allocation_method": self.config.allocation_method.value,
            },
            "timing": {
                "start": self.start_time.isoformat(),
                "end": self.end_time.isoformat(),
                "duration_seconds": self.duration.total_seconds(),
            },
            "summary": {
                "total_tasks": self.total_tasks,
                "completed_tasks": self.completed_tasks,
                "failed_tasks": self.failed_tasks,
                "completion_rate": self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0,
                "total_bids": self.total_bids,
                "total_transacted": self.total_transacted,
                "avg_price": self.total_transacted / self.completed_tasks if self.completed_tasks > 0 else 0,
            },
            "agent_stats": self.agent_stats,
            "time_series": self.time_series,
        }

    def save(self, path: Path | None = None) -> Path:
        """Save results to JSON file."""
        if path is None:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
            path = output_dir / f"{self.config.name}_{timestamp}.json"

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        return path


class ExperimentRunner:
    """Runs experiments with synthetic agents."""

    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config
        self.client = MarketClient(server_url=config.server_url)
        self.metrics = MetricsCollector()
        self.agents: list[SyntheticAgent] = []
        self._running = False
        self._task_generator_task: asyncio.Task | None = None

    async def setup(self) -> None:
        """Set up the experiment."""
        console.print(f"[bold]Setting up experiment: {self.config.name}[/bold]")

        # Connect to market
        await self.client.connect()

        # Create agents
        for agent_config in self.config.agent_configs:
            agent = SyntheticAgent(
                config=agent_config,
                server_url=self.config.server_url,
            )
            self.agents.append(agent)

        console.print(f"  Created {len(self.agents)} synthetic agents")

    async def run(self) -> ExperimentResults:
        """Run the experiment."""
        await self.setup()

        start_time = datetime.utcnow()
        console.print(f"\n[bold green]Starting experiment at {start_time}[/bold green]")
        console.print(f"  Duration: {self.config.duration_seconds}s")
        console.print(f"  Agents: {len(self.agents)}")
        console.print(f"  Task rate: {self.config.tasks_per_minute}/min")

        self._running = True

        # Start agents
        for agent in self.agents:
            await agent.start()

        # Start task generator
        self._task_generator_task = asyncio.create_task(self._generate_tasks())

        # Run for duration
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Running experiment ({self.config.duration_seconds}s)...",
                total=self.config.duration_seconds,
            )

            for i in range(self.config.duration_seconds):
                await asyncio.sleep(1)
                progress.update(task, advance=1)

                # Collect metrics periodically
                if i % 10 == 0:
                    await self._collect_metrics_snapshot()

        self._running = False
        end_time = datetime.utcnow()

        # Stop everything
        if self._task_generator_task:
            self._task_generator_task.cancel()
            try:
                await self._task_generator_task
            except asyncio.CancelledError:
                pass

        for agent in self.agents:
            await agent.stop()

        # Collect final stats
        stats = await self.client.get_stats()
        results = await self._compile_results(start_time, end_time, stats)

        # Save results
        output_path = results.save()
        console.print(f"\n[green]Results saved to: {output_path}[/green]")

        # Print summary
        self._print_summary(results)

        await self.client.disconnect()
        return results

    async def _generate_tasks(self) -> None:
        """Generate tasks at the configured rate."""
        import random
        from examples.sample_tasks import SIMPLE_TASKS, CODING_TASKS, RESEARCH_TASKS

        task_pools = {
            "simple": SIMPLE_TASKS,
            "coding": CODING_TASKS,
            "research": RESEARCH_TASKS,
        }

        interval = 60.0 / self.config.tasks_per_minute

        while self._running:
            try:
                # Pick a random task type
                task_type = random.choice(self.config.task_types)
                pool = task_pools.get(task_type, SIMPLE_TASKS)

                # Pick a random task
                task_data = random.choice(pool)

                # Randomize budget within range
                min_b, max_b = self.config.task_budget_range
                budget = random.uniform(min_b, max_b)

                # Publish
                # Ensure auction duration is at least 1 minute (server expects int)
                auction_minutes = max(1, int(self.config.auction_duration_seconds / 60))
                await self.client.publish_task(
                    title=task_data["title"],
                    description=task_data["description"],
                    budget_max=budget,
                    required_capabilities=task_data.get("required_capabilities", []),
                    auction_duration_minutes=auction_minutes,
                    allocation_method=self.config.allocation_method.value,
                )

                self.metrics.record_event("task_published")

                await asyncio.sleep(interval)

            except Exception as e:
                console.print(f"[yellow]Task generation error: {e}[/yellow]")
                await asyncio.sleep(1)

    async def _collect_metrics_snapshot(self) -> None:
        """Collect a metrics snapshot."""
        try:
            stats = await self.client.get_stats()
            self.metrics.record_snapshot(stats)
        except Exception:
            pass

    async def _compile_results(
        self, start: datetime, end: datetime, final_stats: dict
    ) -> ExperimentResults:
        """Compile experiment results."""
        market = final_stats.get("market", {})
        econ = market.get("economics", {})

        results = ExperimentResults(
            config=self.config,
            start_time=start,
            end_time=end,
            duration=end - start,
            total_tasks=market.get("tasks", {}).get("total", 0),
            completed_tasks=market.get("tasks", {}).get("completed", 0),
            failed_tasks=market.get("tasks", {}).get("failed", 0),
            total_bids=market.get("bids", {}).get("total", 0),
            total_transacted=econ.get("total_transacted", 0),
            time_series=self.metrics.get_time_series(),
        )

        # Collect per-agent stats
        for agent in self.agents:
            results.agent_stats[agent.config.name] = {
                "tasks_completed": agent.tasks_completed,
                "tasks_failed": agent.tasks_failed,
                "total_earned": agent.total_earned,
                "bids_submitted": agent.bids_submitted,
            }

        return results

    def _print_summary(self, results: ExperimentResults) -> None:
        """Print experiment summary."""
        console.print("\n" + "=" * 50)
        console.print("[bold]Experiment Summary[/bold]")
        console.print("=" * 50)

        # Overall stats
        console.print(f"""
Duration: {results.duration.total_seconds():.0f}s
Total tasks: {results.total_tasks}
Completed: {results.completed_tasks}
Failed: {results.failed_tasks}
Completion rate: {results.completed_tasks / results.total_tasks * 100:.1f}%
Total transacted: ${results.total_transacted:.2f}
""")

        # Agent leaderboard
        if results.agent_stats:
            table = Table(title="Agent Performance")
            table.add_column("Agent")
            table.add_column("Completed")
            table.add_column("Failed")
            table.add_column("Earned")

            for name, stats in sorted(
                results.agent_stats.items(),
                key=lambda x: x[1].get("total_earned", 0),
                reverse=True,
            ):
                table.add_row(
                    name,
                    str(stats.get("tasks_completed", 0)),
                    str(stats.get("tasks_failed", 0)),
                    f"${stats.get('total_earned', 0):.2f}",
                )

            console.print(table)


async def run_experiment(config: ExperimentConfig) -> ExperimentResults:
    """Convenience function to run an experiment."""
    runner = ExperimentRunner(config)
    return await runner.run()
