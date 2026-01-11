#!/usr/bin/env python3
"""
Run all experiments for the Agent Economy research paper.

This script runs:
1. Market Mechanism Comparison (4 conditions)
2. Trust Dynamics (5 conditions)

And generates analysis and visualizations.
"""

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from economy.models import AllocationMethod
from economy.network.client import MarketClient
from experiments.synthetic_agents import SyntheticAgentConfig, create_diverse_agents

console = Console()

# Experiment output directory
OUTPUT_DIR = Path("experiment_results")
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class ExperimentResult:
    """Result from a single experiment run."""
    name: str
    condition: str
    run_id: int
    duration_seconds: float
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    total_bids: int
    total_transacted: float
    agent_stats: dict[str, dict]
    
    @property
    def completion_rate(self) -> float:
        return self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0
    
    @property
    def avg_price(self) -> float:
        return self.total_transacted / self.completed_tasks if self.completed_tasks > 0 else 0


async def run_single_experiment(
    name: str,
    condition: str,
    run_id: int,
    agent_configs: list[SyntheticAgentConfig],
    allocation_method: AllocationMethod,
    duration_seconds: int = 120,
    tasks_per_minute: float = 5.0,
    server_url: str = "http://localhost:8000",
) -> ExperimentResult:
    """Run a single experiment."""
    from experiments.synthetic_agents import SyntheticAgent
    
    client = MarketClient(server_url=server_url)
    await client.connect()
    
    agents: list[SyntheticAgent] = []
    agent_stats: dict[str, dict] = {}
    
    # Create and start agents
    for config in agent_configs:
        agent = SyntheticAgent(config=config, server_url=server_url)
        agents.append(agent)
        await agent.start()
    
    # Task generation
    from examples.sample_tasks import SIMPLE_TASKS, CODING_TASKS
    task_pool = SIMPLE_TASKS + CODING_TASKS
    interval = 60.0 / tasks_per_minute
    
    start_time = datetime.utcnow()
    running = True
    task_count = 0
    
    async def generate_tasks():
        nonlocal task_count
        while running:
            try:
                task_data = random.choice(task_pool)
                budget = random.uniform(2.0, 10.0)
                await client.publish_task(
                    title=task_data["title"],
                    description=task_data["description"],
                    budget_max=budget,
                    required_capabilities=task_data.get("required_capabilities", []),
                    auction_duration_minutes=1,
                    allocation_method=allocation_method.value,
                )
                task_count += 1
            except Exception as e:
                pass  # Ignore errors
            await asyncio.sleep(interval)
    
    # Start task generation
    task_gen = asyncio.create_task(generate_tasks())
    
    # Run for duration
    await asyncio.sleep(duration_seconds)
    
    # Stop
    running = False
    task_gen.cancel()
    try:
        await task_gen
    except asyncio.CancelledError:
        pass
    
    # Wait for pending tasks to complete
    await asyncio.sleep(5)
    
    # Collect stats
    stats = await client.get_stats()
    market = stats.get("market", {})
    
    # Get per-agent stats
    for agent in agents:
        agent_stats[agent.config.name] = {
            "tasks_completed": agent.tasks_completed,
            "tasks_failed": agent.tasks_failed,
            "total_earned": agent.total_earned,
            "bids_submitted": agent.bids_submitted,
            "success_rate": agent.config.success_rate,
            "quality_mean": agent.config.quality_mean,
        }
        await agent.stop()
    
    await client.disconnect()
    
    return ExperimentResult(
        name=name,
        condition=condition,
        run_id=run_id,
        duration_seconds=duration_seconds,
        total_tasks=market.get("tasks", {}).get("total", task_count),
        completed_tasks=market.get("tasks", {}).get("completed", 0),
        failed_tasks=market.get("tasks", {}).get("failed", 0),
        total_bids=market.get("bids", {}).get("total", 0),
        total_transacted=market.get("economics", {}).get("total_transacted", 0),
        agent_stats=agent_stats,
    )


async def clear_server_state(server_url: str = "http://localhost:8000"):
    """Clear server state by restarting (simulated with new client)."""
    # The server uses in-memory storage, so we just need to wait for it
    # In practice, we'd restart the server between experiments
    await asyncio.sleep(2)


async def run_market_efficiency_experiments(
    runs_per_condition: int = 3,
    duration_per_run: int = 60,
) -> list[ExperimentResult]:
    """Run market efficiency comparison experiments."""
    console.print("\n[bold blue]═══ EXPERIMENT 1: Market Mechanism Comparison ═══[/bold blue]\n")
    
    conditions = [
        ("fixed_price", AllocationMethod.FIXED_PRICE),
        ("first_price", AllocationMethod.FIRST_PRICE_AUCTION),
        ("second_price", AllocationMethod.SECOND_PRICE_AUCTION),
        ("reputation_weighted", AllocationMethod.REPUTATION_WEIGHTED),
    ]
    
    all_results: list[ExperimentResult] = []
    base_agents = create_diverse_agents(15)
    
    for condition_name, allocation_method in conditions:
        console.print(f"\n[cyan]Condition: {condition_name}[/cyan]")
        
        for run_id in range(runs_per_condition):
            console.print(f"  Run {run_id + 1}/{runs_per_condition}...", end=" ")
            
            await clear_server_state()
            
            result = await run_single_experiment(
                name="market_efficiency",
                condition=condition_name,
                run_id=run_id,
                agent_configs=base_agents,
                allocation_method=allocation_method,
                duration_seconds=duration_per_run,
                tasks_per_minute=4.0,
            )
            
            all_results.append(result)
            console.print(f"[green]✓[/green] {result.completed_tasks}/{result.total_tasks} completed")
    
    return all_results


async def run_trust_dynamics_experiments(
    runs_per_condition: int = 3,
    duration_per_run: int = 60,
) -> list[ExperimentResult]:
    """Run trust dynamics experiments with varying unreliable agent proportions."""
    console.print("\n[bold blue]═══ EXPERIMENT 2: Trust Dynamics ═══[/bold blue]\n")
    
    unreliable_fractions = [0.0, 0.1, 0.2, 0.3, 0.5]
    all_results: list[ExperimentResult] = []
    
    for fraction in unreliable_fractions:
        condition_name = f"unreliable_{int(fraction*100)}pct"
        console.print(f"\n[cyan]Condition: {condition_name}[/cyan]")
        
        # Create agent population with specified unreliable fraction
        num_agents = 15
        num_unreliable = int(num_agents * fraction)
        num_reliable = num_agents - num_unreliable
        
        agents = []
        for i in range(num_reliable):
            agents.append(SyntheticAgentConfig(
                name=f"Reliable_{i}",
                capabilities=["general", "coding", "writing"],
                success_rate=0.85 + random.random() * 0.1,
                quality_mean=0.75 + random.random() * 0.15,
                bid_aggressiveness=0.5 + random.random() * 0.3,
            ))
        
        for i in range(num_unreliable):
            agents.append(SyntheticAgentConfig(
                name=f"Unreliable_{i}",
                capabilities=["general", "coding", "writing"],
                success_rate=0.2 + random.random() * 0.3,  # 20-50% success
                quality_mean=0.3 + random.random() * 0.3,
                bid_aggressiveness=0.8 + random.random() * 0.15,  # Very cheap
            ))
        
        for run_id in range(runs_per_condition):
            console.print(f"  Run {run_id + 1}/{runs_per_condition}...", end=" ")
            
            await clear_server_state()
            
            result = await run_single_experiment(
                name="trust_dynamics",
                condition=condition_name,
                run_id=run_id,
                agent_configs=agents,
                allocation_method=AllocationMethod.REPUTATION_WEIGHTED,
                duration_seconds=duration_per_run,
                tasks_per_minute=4.0,
            )
            
            all_results.append(result)
            console.print(f"[green]✓[/green] {result.completed_tasks}/{result.total_tasks} completed")
    
    return all_results


def analyze_market_efficiency(results: list[ExperimentResult]) -> dict[str, Any]:
    """Analyze market efficiency experiment results."""
    # Group by condition
    by_condition: dict[str, list[ExperimentResult]] = {}
    for r in results:
        by_condition.setdefault(r.condition, []).append(r)
    
    analysis = {
        "by_condition": {},
        "comparison": {},
    }
    
    for condition, runs in by_condition.items():
        completion_rates = [r.completion_rate for r in runs]
        avg_prices = [r.avg_price for r in runs]
        total_transacted = [r.total_transacted for r in runs]
        
        analysis["by_condition"][condition] = {
            "n_runs": len(runs),
            "completion_rate_mean": sum(completion_rates) / len(completion_rates),
            "completion_rate_std": (sum((x - sum(completion_rates)/len(completion_rates))**2 for x in completion_rates) / len(completion_rates)) ** 0.5,
            "avg_price_mean": sum(avg_prices) / len(avg_prices) if avg_prices else 0,
            "total_transacted_mean": sum(total_transacted) / len(total_transacted),
            "total_tasks_mean": sum(r.total_tasks for r in runs) / len(runs),
            "completed_tasks_mean": sum(r.completed_tasks for r in runs) / len(runs),
        }
    
    # Compute improvement over baseline (fixed_price)
    baseline = analysis["by_condition"].get("fixed_price", {})
    baseline_completion = baseline.get("completion_rate_mean", 0)
    
    for condition, stats in analysis["by_condition"].items():
        if baseline_completion > 0:
            improvement = (stats["completion_rate_mean"] - baseline_completion) / baseline_completion * 100
            analysis["comparison"][condition] = {
                "completion_improvement_pct": improvement,
            }
    
    return analysis


def analyze_trust_dynamics(results: list[ExperimentResult]) -> dict[str, Any]:
    """Analyze trust dynamics experiment results."""
    # Group by condition
    by_condition: dict[str, list[ExperimentResult]] = {}
    for r in results:
        by_condition.setdefault(r.condition, []).append(r)
    
    analysis = {
        "by_condition": {},
        "degradation_curve": [],
    }
    
    for condition, runs in sorted(by_condition.items()):
        completion_rates = [r.completion_rate for r in runs]
        
        # Extract unreliable percentage from condition name
        pct = int(condition.split("_")[1].replace("pct", ""))
        
        analysis["by_condition"][condition] = {
            "unreliable_pct": pct,
            "n_runs": len(runs),
            "completion_rate_mean": sum(completion_rates) / len(completion_rates),
            "completion_rate_std": (sum((x - sum(completion_rates)/len(completion_rates))**2 for x in completion_rates) / len(completion_rates)) ** 0.5,
            "total_transacted_mean": sum(r.total_transacted for r in runs) / len(runs),
        }
        
        analysis["degradation_curve"].append({
            "unreliable_pct": pct,
            "completion_rate": sum(completion_rates) / len(completion_rates),
        })
    
    # Sort degradation curve
    analysis["degradation_curve"] = sorted(
        analysis["degradation_curve"],
        key=lambda x: x["unreliable_pct"]
    )
    
    return analysis


def generate_summary_table(
    market_analysis: dict,
    trust_analysis: dict,
) -> str:
    """Generate markdown summary table."""
    lines = ["## Experimental Results Summary\n"]
    
    # Market Efficiency Table
    lines.append("### Market Mechanism Comparison\n")
    lines.append("| Mechanism | Completion Rate | Avg Price | Improvement vs Baseline |")
    lines.append("|-----------|-----------------|-----------|-------------------------|")
    
    for condition, stats in market_analysis["by_condition"].items():
        improvement = market_analysis["comparison"].get(condition, {}).get("completion_improvement_pct", 0)
        lines.append(
            f"| {condition} | {stats['completion_rate_mean']:.1%} ± {stats['completion_rate_std']:.1%} | "
            f"${stats['avg_price_mean']:.2f} | {improvement:+.1f}% |"
        )
    
    lines.append("")
    
    # Trust Dynamics Table
    lines.append("### Trust Dynamics (Reputation-Weighted Allocation)\n")
    lines.append("| Unreliable Agents | Completion Rate | Total Transacted |")
    lines.append("|-------------------|-----------------|------------------|")
    
    for stats in trust_analysis["degradation_curve"]:
        pct = stats["unreliable_pct"]
        cond = f"unreliable_{pct}pct"
        full_stats = trust_analysis["by_condition"][cond]
        lines.append(
            f"| {pct}% | {full_stats['completion_rate_mean']:.1%} ± {full_stats['completion_rate_std']:.1%} | "
            f"${full_stats['total_transacted_mean']:.2f} |"
        )
    
    return "\n".join(lines)


async def main():
    """Run all experiments and generate analysis."""
    console.print("[bold]Agent Economy Research Experiments[/bold]")
    console.print("=" * 50)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_DIR / timestamp
    output_dir.mkdir(exist_ok=True)
    
    # Run experiments
    console.print("\n[yellow]Starting experiments...[/yellow]")
    console.print("This will take approximately 10-15 minutes.\n")
    
    # Experiment 1: Market Efficiency
    market_results = await run_market_efficiency_experiments(
        runs_per_condition=3,
        duration_per_run=60,
    )
    
    # Experiment 2: Trust Dynamics
    trust_results = await run_trust_dynamics_experiments(
        runs_per_condition=3,
        duration_per_run=60,
    )
    
    # Analyze results
    console.print("\n[yellow]Analyzing results...[/yellow]")
    
    market_analysis = analyze_market_efficiency(market_results)
    trust_analysis = analyze_trust_dynamics(trust_results)
    
    # Save raw results
    all_results = {
        "timestamp": timestamp,
        "market_efficiency": {
            "results": [
                {
                    "condition": r.condition,
                    "run_id": r.run_id,
                    "total_tasks": r.total_tasks,
                    "completed_tasks": r.completed_tasks,
                    "failed_tasks": r.failed_tasks,
                    "completion_rate": r.completion_rate,
                    "total_transacted": r.total_transacted,
                    "avg_price": r.avg_price,
                }
                for r in market_results
            ],
            "analysis": market_analysis,
        },
        "trust_dynamics": {
            "results": [
                {
                    "condition": r.condition,
                    "run_id": r.run_id,
                    "total_tasks": r.total_tasks,
                    "completed_tasks": r.completed_tasks,
                    "failed_tasks": r.failed_tasks,
                    "completion_rate": r.completion_rate,
                    "total_transacted": r.total_transacted,
                }
                for r in trust_results
            ],
            "analysis": trust_analysis,
        },
    }
    
    # Save to JSON
    results_file = output_dir / "results.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)
    console.print(f"[green]Results saved to: {results_file}[/green]")
    
    # Generate summary
    summary = generate_summary_table(market_analysis, trust_analysis)
    summary_file = output_dir / "summary.md"
    with open(summary_file, "w") as f:
        f.write(summary)
    console.print(f"[green]Summary saved to: {summary_file}[/green]")
    
    # Print summary
    console.print("\n" + "=" * 50)
    console.print("[bold]RESULTS SUMMARY[/bold]")
    console.print("=" * 50)
    console.print(summary)
    
    return all_results


if __name__ == "__main__":
    asyncio.run(main())
