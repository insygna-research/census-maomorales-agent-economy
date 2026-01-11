"""Enhanced metrics collection and analysis for experiments."""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class DetailedMetrics:
    """Detailed metrics for research analysis."""

    # Per-task metrics
    time_to_first_bid: list[float] = field(default_factory=list)
    time_to_allocation: list[float] = field(default_factory=list)
    bid_count_per_task: list[int] = field(default_factory=list)
    price_vs_budget_ratio: list[float] = field(default_factory=list)
    task_quality_scores: list[float] = field(default_factory=list)

    # Per-agent metrics
    agent_bids_submitted: dict[str, int] = field(default_factory=dict)
    agent_bids_won: dict[str, int] = field(default_factory=dict)
    agent_tasks_completed: dict[str, int] = field(default_factory=dict)
    agent_tasks_failed: dict[str, int] = field(default_factory=dict)
    agent_earnings: dict[str, float] = field(default_factory=dict)
    agent_quality_scores: dict[str, list[float]] = field(default_factory=dict)

    # Time-series data
    reputation_over_time: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    earnings_over_time: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    tasks_completed_over_time: list[tuple[float, int]] = field(default_factory=list)
    market_volume_over_time: list[tuple[float, float]] = field(default_factory=list)

    def record_bid(self, agent_id: str, task_id: str, time_since_publish: float) -> None:
        """Record a bid submission."""
        self.agent_bids_submitted[agent_id] = self.agent_bids_submitted.get(agent_id, 0) + 1
        if not self.time_to_first_bid or len(self.time_to_first_bid) < 1:
            self.time_to_first_bid.append(time_since_publish)

    def record_allocation(
        self,
        winner_id: str,
        price: float,
        budget_max: float,
        time_to_allocate: float,
        bid_count: int,
    ) -> None:
        """Record a task allocation."""
        self.agent_bids_won[winner_id] = self.agent_bids_won.get(winner_id, 0) + 1
        self.time_to_allocation.append(time_to_allocate)
        self.bid_count_per_task.append(bid_count)
        if budget_max > 0:
            self.price_vs_budget_ratio.append(price / budget_max)

    def record_completion(
        self,
        agent_id: str,
        earnings: float,
        quality_score: float,
        elapsed_time: float,
    ) -> None:
        """Record a task completion."""
        self.agent_tasks_completed[agent_id] = self.agent_tasks_completed.get(agent_id, 0) + 1
        self.agent_earnings[agent_id] = self.agent_earnings.get(agent_id, 0) + earnings

        if agent_id not in self.agent_quality_scores:
            self.agent_quality_scores[agent_id] = []
        self.agent_quality_scores[agent_id].append(quality_score)
        self.task_quality_scores.append(quality_score)

        # Record time-series
        self.earnings_over_time.setdefault(agent_id, []).append((elapsed_time, earnings))

    def record_failure(self, agent_id: str) -> None:
        """Record a task failure."""
        self.agent_tasks_failed[agent_id] = self.agent_tasks_failed.get(agent_id, 0) + 1

    def record_reputation(self, agent_id: str, score: float, elapsed_time: float) -> None:
        """Record reputation at a point in time."""
        self.reputation_over_time.setdefault(agent_id, []).append((elapsed_time, score))

    def compute_win_rates(self) -> dict[str, float]:
        """Compute win rate for each agent."""
        win_rates = {}
        for agent_id, bids in self.agent_bids_submitted.items():
            wins = self.agent_bids_won.get(agent_id, 0)
            win_rates[agent_id] = wins / bids if bids > 0 else 0
        return win_rates

    def compute_gini_coefficient(self) -> float:
        """Compute Gini coefficient for earnings inequality."""
        earnings = list(self.agent_earnings.values())
        if not earnings or sum(earnings) == 0:
            return 0.0

        sorted_earnings = sorted(earnings)
        n = len(sorted_earnings)
        cumulative = sum((i + 1) * e for i, e in enumerate(sorted_earnings))
        return (2 * cumulative) / (n * sum(sorted_earnings)) - (n + 1) / n

    def compute_market_efficiency(self, total_budget: float) -> float:
        """Compute market efficiency as value created / potential value."""
        total_earnings = sum(self.agent_earnings.values())
        return total_earnings / total_budget if total_budget > 0 else 0

    def compute_average_quality(self) -> float:
        """Compute average quality score."""
        if not self.task_quality_scores:
            return 0.0
        return sum(self.task_quality_scores) / len(self.task_quality_scores)

    def compute_completion_rate(self) -> float:
        """Compute overall completion rate."""
        completed = sum(self.agent_tasks_completed.values())
        failed = sum(self.agent_tasks_failed.values())
        total = completed + failed
        return completed / total if total > 0 else 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_metrics": {
                "time_to_first_bid_mean": sum(self.time_to_first_bid) / len(self.time_to_first_bid) if self.time_to_first_bid else 0,
                "time_to_allocation_mean": sum(self.time_to_allocation) / len(self.time_to_allocation) if self.time_to_allocation else 0,
                "bid_count_mean": sum(self.bid_count_per_task) / len(self.bid_count_per_task) if self.bid_count_per_task else 0,
                "price_ratio_mean": sum(self.price_vs_budget_ratio) / len(self.price_vs_budget_ratio) if self.price_vs_budget_ratio else 0,
                "quality_mean": self.compute_average_quality(),
            },
            "agent_metrics": {
                "win_rates": self.compute_win_rates(),
                "earnings": self.agent_earnings,
                "completed": self.agent_tasks_completed,
                "failed": self.agent_tasks_failed,
            },
            "market_metrics": {
                "gini_coefficient": self.compute_gini_coefficient(),
                "completion_rate": self.compute_completion_rate(),
            },
        }


@dataclass
class MetricsCollector:
    """Collects and stores metrics during experiments."""

    events: list[dict] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    detailed: DetailedMetrics = field(default_factory=DetailedMetrics)
    start_time: datetime | None = None

    def set_start_time(self, t: datetime) -> None:
        """Set experiment start time."""
        self.start_time = t

    def elapsed_seconds(self) -> float:
        """Get elapsed time since start."""
        if not self.start_time:
            return 0.0
        return (datetime.utcnow() - self.start_time).total_seconds()

    def record_event(self, event_type: str, data: dict | None = None) -> None:
        """Record a single event."""
        self.events.append({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed": self.elapsed_seconds(),
            "data": data or {},
        })
        self.counters[event_type] = self.counters.get(event_type, 0) + 1

    def record_snapshot(self, stats: dict) -> None:
        """Record a metrics snapshot."""
        self.snapshots.append({
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed": self.elapsed_seconds(),
            "stats": stats,
        })

    def get_time_series(self) -> list[dict]:
        """Get time series data from snapshots."""
        series = []
        for snapshot in self.snapshots:
            market = snapshot["stats"].get("market", {})
            series.append({
                "timestamp": snapshot["timestamp"],
                "elapsed": snapshot["elapsed"],
                "tasks_total": market.get("tasks", {}).get("total", 0),
                "tasks_completed": market.get("tasks", {}).get("completed", 0),
                "tasks_open": market.get("tasks", {}).get("open", 0),
                "agents_online": market.get("agents", {}).get("online", 0),
                "total_transacted": market.get("economics", {}).get("total_transacted", 0),
            })
        return series

    def get_event_counts(self) -> dict[str, int]:
        """Get event counts by type."""
        return self.counters.copy()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of collected metrics."""
        return {
            "total_events": len(self.events),
            "total_snapshots": len(self.snapshots),
            "event_counts": self.get_event_counts(),
            "detailed": self.detailed.to_dict(),
        }

    def clear(self) -> None:
        """Clear all collected metrics."""
        self.events.clear()
        self.snapshots.clear()
        self.counters.clear()
        self.detailed = DetailedMetrics()
        self.start_time = None


def analyze_experiment_results(results_path: str) -> dict[str, Any]:
    """Analyze experiment results from a JSON file."""
    with open(results_path) as f:
        data = json.load(f)

    summary = data.get("summary", {})
    time_series = data.get("time_series", [])
    agent_stats = data.get("agent_stats", {})

    analysis = {
        "overview": summary,
        "efficiency": {},
        "agent_analysis": {},
    }

    # Calculate efficiency metrics
    if summary.get("total_tasks", 0) > 0:
        analysis["efficiency"]["completion_rate"] = summary.get("completion_rate", 0)
        analysis["efficiency"]["avg_price"] = summary.get("avg_price", 0)

    # Analyze agent performance
    if agent_stats:
        earnings = [(name, stats.get("total_earned", 0)) for name, stats in agent_stats.items()]
        earnings.sort(key=lambda x: x[1], reverse=True)

        analysis["agent_analysis"]["top_earners"] = earnings[:5]
        analysis["agent_analysis"]["total_agents"] = len(agent_stats)

        # Calculate Gini coefficient for earnings distribution
        if earnings:
            sorted_earnings = sorted([e[1] for e in earnings])
            n = len(sorted_earnings)
            if n > 1 and sum(sorted_earnings) > 0:
                cumulative = sum((i + 1) * e for i, e in enumerate(sorted_earnings))
                gini = (2 * cumulative) / (n * sum(sorted_earnings)) - (n + 1) / n
                analysis["agent_analysis"]["earnings_gini"] = gini

    # Analyze time series trends
    if len(time_series) > 1:
        first = time_series[0]
        last = time_series[-1]

        analysis["trends"] = {
            "tasks_growth": last.get("tasks_total", 0) - first.get("tasks_total", 0),
            "completion_growth": last.get("tasks_completed", 0) - first.get("tasks_completed", 0),
        }

    return analysis


def compare_experiments(result_paths: list[str]) -> dict[str, Any]:
    """Compare multiple experiment results."""
    experiments = []
    for path in result_paths:
        with open(path) as f:
            data = json.load(f)
            experiments.append({
                "name": data.get("config", {}).get("name", "Unknown"),
                "completion_rate": data.get("summary", {}).get("completion_rate", 0),
                "avg_price": data.get("summary", {}).get("avg_price", 0),
                "total_transacted": data.get("summary", {}).get("total_transacted", 0),
                "total_tasks": data.get("summary", {}).get("total_tasks", 0),
            })

    # Rank by different metrics
    comparison = {
        "experiments": experiments,
        "rankings": {
            "by_completion_rate": sorted(
                experiments, key=lambda x: x["completion_rate"], reverse=True
            ),
            "by_efficiency": sorted(
                experiments,
                key=lambda x: x["total_transacted"] / max(x["total_tasks"], 1),
                reverse=True,
            ),
        },
    }

    return comparison


def compute_statistical_significance(
    group1: list[float],
    group2: list[float],
) -> dict[str, float]:
    """Compute t-test for two groups."""
    from scipy import stats

    if len(group1) < 2 or len(group2) < 2:
        return {"t_statistic": 0, "p_value": 1.0, "significant": False}

    t_stat, p_value = stats.ttest_ind(group1, group2)
    return {
        "t_statistic": t_stat,
        "p_value": p_value,
        "significant": p_value < 0.05,
        "effect_size": (sum(group1)/len(group1) - sum(group2)/len(group2)) / 
                       math.sqrt((sum((x - sum(group1)/len(group1))**2 for x in group1) + 
                                  sum((x - sum(group2)/len(group2))**2 for x in group2)) / 
                                 (len(group1) + len(group2) - 2)) if len(group1) + len(group2) > 2 else 0,
    }
