"""Repository classes for data access."""

import json
from datetime import datetime
from typing import Any

from economy.models import (
    AgentProfile,
    Bid,
    Execution,
    PerformanceRecord,
    ReputationSummary,
    Task,
)
from economy.persistence.database import Database


class AgentRepository:
    """Repository for agent data."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, agent: AgentProfile) -> None:
        """Save or update an agent."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO agents 
            (agent_id, name, description, profile_json, registered_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent.agent_id,
                agent.name,
                agent.description,
                agent.model_dump_json(),
                agent.registered_at.isoformat(),
                agent.last_seen.isoformat(),
            ),
        )
        await self.db.commit()

    async def get(self, agent_id: str) -> AgentProfile | None:
        """Get an agent by ID."""
        row = await self.db.fetchone(
            "SELECT profile_json FROM agents WHERE agent_id = ?",
            (agent_id,),
        )
        if row:
            return AgentProfile.model_validate_json(row["profile_json"])
        return None

    async def get_all(self) -> list[AgentProfile]:
        """Get all agents."""
        rows = await self.db.fetchall("SELECT profile_json FROM agents")
        return [AgentProfile.model_validate_json(row["profile_json"]) for row in rows]

    async def delete(self, agent_id: str) -> None:
        """Delete an agent."""
        await self.db.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
        await self.db.commit()

    async def update_last_seen(self, agent_id: str) -> None:
        """Update agent's last seen timestamp."""
        await self.db.execute(
            "UPDATE agents SET last_seen = ? WHERE agent_id = ?",
            (datetime.utcnow().isoformat(), agent_id),
        )
        await self.db.commit()


class TaskRepository:
    """Repository for task data."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, task: Task) -> None:
        """Save or update a task."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO tasks 
            (task_id, publisher_id, title, status, allocation_method, 
             budget_max, task_json, created_at, published_at, assigned_at,
             completed_at, assigned_agent_id, final_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.publisher_id,
                task.specification.title,
                task.status.value,
                task.allocation_method.value,
                task.budget.max_price,
                task.model_dump_json(),
                task.created_at.isoformat(),
                task.published_at.isoformat() if task.published_at else None,
                task.assigned_at.isoformat() if task.assigned_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                task.assigned_agent_id,
                task.final_price,
            ),
        )
        await self.db.commit()

    async def get(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        row = await self.db.fetchone(
            "SELECT task_json FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        if row:
            return Task.model_validate_json(row["task_json"])
        return None

    async def get_all(self) -> list[Task]:
        """Get all tasks."""
        rows = await self.db.fetchall("SELECT task_json FROM tasks ORDER BY created_at DESC")
        return [Task.model_validate_json(row["task_json"]) for row in rows]

    async def get_by_status(self, status: str) -> list[Task]:
        """Get tasks by status."""
        rows = await self.db.fetchall(
            "SELECT task_json FROM tasks WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [Task.model_validate_json(row["task_json"]) for row in rows]

    async def get_by_publisher(self, publisher_id: str) -> list[Task]:
        """Get tasks by publisher."""
        rows = await self.db.fetchall(
            "SELECT task_json FROM tasks WHERE publisher_id = ? ORDER BY created_at DESC",
            (publisher_id,),
        )
        return [Task.model_validate_json(row["task_json"]) for row in rows]


class BidRepository:
    """Repository for bid data."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, bid: Bid) -> None:
        """Save or update a bid."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO bids 
            (bid_id, task_id, agent_id, price, status, bid_json, submitted_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bid.bid_id,
                bid.task_id,
                bid.agent_id,
                bid.price,
                bid.status.value,
                bid.model_dump_json(),
                bid.submitted_at.isoformat(),
                bid.resolved_at.isoformat() if bid.resolved_at else None,
            ),
        )
        await self.db.commit()

    async def get(self, bid_id: str) -> Bid | None:
        """Get a bid by ID."""
        row = await self.db.fetchone(
            "SELECT bid_json FROM bids WHERE bid_id = ?",
            (bid_id,),
        )
        if row:
            return Bid.model_validate_json(row["bid_json"])
        return None

    async def get_for_task(self, task_id: str) -> list[Bid]:
        """Get all bids for a task."""
        rows = await self.db.fetchall(
            "SELECT bid_json FROM bids WHERE task_id = ? ORDER BY submitted_at",
            (task_id,),
        )
        return [Bid.model_validate_json(row["bid_json"]) for row in rows]

    async def get_for_agent(self, agent_id: str) -> list[Bid]:
        """Get all bids by an agent."""
        rows = await self.db.fetchall(
            "SELECT bid_json FROM bids WHERE agent_id = ? ORDER BY submitted_at DESC",
            (agent_id,),
        )
        return [Bid.model_validate_json(row["bid_json"]) for row in rows]


class ExecutionRepository:
    """Repository for execution data."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, execution: Execution) -> None:
        """Save or update an execution."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO executions 
            (execution_id, task_id, agent_id, bid_id, agreed_price, status,
             execution_json, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.execution_id,
                execution.task_id,
                execution.agent_id,
                execution.bid_id,
                execution.agreed_price,
                execution.status.value,
                execution.model_dump_json(),
                execution.started_at.isoformat() if execution.started_at else None,
                execution.completed_at.isoformat() if execution.completed_at else None,
            ),
        )
        await self.db.commit()

    async def get(self, execution_id: str) -> Execution | None:
        """Get an execution by ID."""
        row = await self.db.fetchone(
            "SELECT execution_json FROM executions WHERE execution_id = ?",
            (execution_id,),
        )
        if row:
            return Execution.model_validate_json(row["execution_json"])
        return None

    async def get_for_task(self, task_id: str) -> Execution | None:
        """Get the execution for a task."""
        row = await self.db.fetchone(
            "SELECT execution_json FROM executions WHERE task_id = ?",
            (task_id,),
        )
        if row:
            return Execution.model_validate_json(row["execution_json"])
        return None

    async def get_for_agent(self, agent_id: str) -> list[Execution]:
        """Get all executions by an agent."""
        rows = await self.db.fetchall(
            "SELECT execution_json FROM executions WHERE agent_id = ? ORDER BY started_at DESC",
            (agent_id,),
        )
        return [Execution.model_validate_json(row["execution_json"]) for row in rows]

    async def get_all(self) -> list[Execution]:
        """Get all executions."""
        rows = await self.db.fetchall(
            "SELECT execution_json FROM executions ORDER BY started_at DESC"
        )
        return [Execution.model_validate_json(row["execution_json"]) for row in rows]

    async def get_by_status(self, status: str) -> list[Execution]:
        """Get executions by status."""
        rows = await self.db.fetchall(
            "SELECT execution_json FROM executions WHERE status = ?",
            (status,),
        )
        return [Execution.model_validate_json(row["execution_json"]) for row in rows]


class ReputationRepository:
    """Repository for reputation data."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save_record(self, record: PerformanceRecord) -> None:
        """Save a performance record."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO performance_records 
            (record_id, agent_id, task_id, execution_id, completed, on_time,
             quality_score, bid_price, final_price, record_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
                record.agent_id,
                record.task_id,
                record.execution_id,
                1 if record.completed else 0,
                1 if record.on_time else 0,
                record.quality_score,
                record.bid_price,
                record.final_price,
                record.model_dump_json(),
                record.timestamp.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_records(
        self, agent_id: str, limit: int = 100
    ) -> list[PerformanceRecord]:
        """Get performance records for an agent."""
        rows = await self.db.fetchall(
            """
            SELECT record_json FROM performance_records 
            WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?
            """,
            (agent_id, limit),
        )
        return [PerformanceRecord.model_validate_json(row["record_json"]) for row in rows]

    async def save_summary(self, summary: ReputationSummary) -> None:
        """Save a reputation summary."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO reputation_summaries 
            (agent_id, overall_score, completion_rate, on_time_rate, 
             average_quality, total_tasks, total_earnings, summary_json, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary.agent_id,
                summary.overall_score,
                summary.completion_rate,
                summary.on_time_rate,
                summary.average_quality,
                summary.total_tasks,
                summary.total_earnings,
                summary.model_dump_json(),
                summary.computed_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_summary(self, agent_id: str) -> ReputationSummary | None:
        """Get a reputation summary for an agent."""
        row = await self.db.fetchone(
            "SELECT summary_json FROM reputation_summaries WHERE agent_id = ?",
            (agent_id,),
        )
        if row:
            return ReputationSummary.model_validate_json(row["summary_json"])
        return None

    async def get_all_summaries(self) -> list[ReputationSummary]:
        """Get all reputation summaries."""
        rows = await self.db.fetchall(
            "SELECT summary_json FROM reputation_summaries ORDER BY overall_score DESC"
        )
        return [ReputationSummary.model_validate_json(row["summary_json"]) for row in rows]

    async def get_score(self, agent_id: str) -> float:
        """Get just the reputation score for an agent."""
        row = await self.db.fetchone(
            "SELECT overall_score FROM reputation_summaries WHERE agent_id = ?",
            (agent_id,),
        )
        return row["overall_score"] if row else 0.5  # Default for new agents

    async def get_all_scores(self) -> dict[str, float]:
        """Get all reputation scores."""
        rows = await self.db.fetchall(
            "SELECT agent_id, overall_score FROM reputation_summaries"
        )
        return {row["agent_id"]: row["overall_score"] for row in rows}


class EventRepository:
    """Repository for event logging."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def log(self, event_type: str, data: dict[str, Any]) -> None:
        """Log an event."""
        await self.db.execute(
            "INSERT INTO events (event_type, timestamp, data_json) VALUES (?, ?, ?)",
            (event_type, datetime.utcnow().isoformat(), json.dumps(data)),
        )
        await self.db.commit()

    async def get_events(
        self,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get events, optionally filtered by type."""
        if event_type:
            rows = await self.db.fetchall(
                """
                SELECT event_type, timestamp, data_json FROM events 
                WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?
                """,
                (event_type, limit),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT event_type, timestamp, data_json FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [
            {
                "type": row["event_type"],
                "timestamp": row["timestamp"],
                "data": json.loads(row["data_json"]),
            }
            for row in rows
        ]

    async def get_stats(self) -> dict[str, int]:
        """Get event counts by type."""
        rows = await self.db.fetchall(
            "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type"
        )
        return {row["event_type"]: row["count"] for row in rows}
