"""Task board - central discovery and coordination mechanism."""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from economy.models import (
    AgentProfile,
    Bid,
    BidStatus,
    Execution,
    ExecutionStatus,
    Task,
    TaskStatus,
)


class TaskBoard:
    """
    Central task board for discovery and coordination.

    This is the heart of the marketplace - agents subscribe to tasks,
    submit bids, and receive updates about task lifecycle events.
    """

    def __init__(self) -> None:
        # Task storage
        self._tasks: dict[str, Task] = {}
        self._bids: dict[str, list[Bid]] = defaultdict(list)  # task_id -> bids
        self._executions: dict[str, Execution] = {}  # execution_id -> execution

        # Agent registry
        self._agents: dict[str, AgentProfile] = {}

        # Subscriptions: capability -> list of callbacks
        self._subscriptions: dict[str, list[Callable]] = defaultdict(list)
        self._global_subscriptions: list[Callable] = []

        # Event log for analysis
        self._event_log: list[dict[str, Any]] = []

        # Locks for thread safety
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # Agent Management
    # -------------------------------------------------------------------------

    async def register_agent(self, profile: AgentProfile) -> None:
        """Register an agent with the marketplace."""
        async with self._lock:
            self._agents[profile.agent_id] = profile
            self._log_event("agent_registered", {"agent_id": profile.agent_id})

    async def update_agent(self, profile: AgentProfile) -> None:
        """Update an agent's profile."""
        async with self._lock:
            if profile.agent_id in self._agents:
                self._agents[profile.agent_id] = profile
                self._log_event("agent_updated", {"agent_id": profile.agent_id})

    async def deregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the marketplace."""
        async with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                self._log_event("agent_deregistered", {"agent_id": agent_id})

    async def heartbeat(self, agent_id: str) -> None:
        """Update agent's last seen timestamp."""
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_seen = datetime.utcnow()

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        """Get an agent's profile."""
        return self._agents.get(agent_id)

    def get_all_agents(self) -> list[AgentProfile]:
        """Get all registered agents."""
        return list(self._agents.values())

    def get_online_agents(self, timeout_seconds: int = 60) -> list[AgentProfile]:
        """Get agents that have been seen recently."""
        cutoff = datetime.utcnow()
        return [
            a for a in self._agents.values()
            if (cutoff - a.last_seen).total_seconds() < timeout_seconds
        ]

    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------

    async def publish_task(self, task: Task) -> str:
        """Publish a task to the marketplace."""
        async with self._lock:
            task.status = TaskStatus.OPEN
            task.published_at = datetime.utcnow()
            self._tasks[task.task_id] = task
            self._log_event("task_published", {
                "task_id": task.task_id,
                "publisher_id": task.publisher_id,
                "budget": task.budget.max_price,
            })

        # Notify subscribers
        await self._notify_subscribers(task)
        return task.task_id

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        """Get all tasks."""
        return list(self._tasks.values())

    def get_open_tasks(self) -> list[Task]:
        """Get all open tasks."""
        return [t for t in self._tasks.values() if t.status == TaskStatus.OPEN]

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Get tasks by status."""
        return [t for t in self._tasks.values() if t.status == status]

    def get_tasks_by_publisher(self, publisher_id: str) -> list[Task]:
        """Get all tasks published by a specific agent."""
        return [t for t in self._tasks.values() if t.publisher_id == publisher_id]

    def get_tasks_for_capability(self, capability: str) -> list[Task]:
        """Get open tasks requiring a specific capability."""
        return [
            t for t in self._tasks.values()
            if t.status == TaskStatus.OPEN
            and capability in t.specification.required_capabilities
        ]

    async def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update a task's status."""
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if status == TaskStatus.COMPLETED:
                    self._tasks[task_id].completed_at = datetime.utcnow()
                self._log_event("task_status_changed", {
                    "task_id": task_id,
                    "status": status.value,
                })

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a task."""
        await self.update_task_status(task_id, TaskStatus.CANCELLED)

    # -------------------------------------------------------------------------
    # Bidding
    # -------------------------------------------------------------------------

    async def submit_bid(self, bid: Bid) -> None:
        """Submit a bid for a task."""
        async with self._lock:
            task = self._tasks.get(bid.task_id)
            if not task:
                raise ValueError(f"Task {bid.task_id} not found")
            if task.status != TaskStatus.OPEN:
                raise ValueError(f"Task {bid.task_id} is not accepting bids")
            if not task.budget.is_acceptable(bid.price):
                raise ValueError(f"Bid price {bid.price} is outside budget")

            self._bids[bid.task_id].append(bid)
            self._log_event("bid_submitted", {
                "bid_id": bid.bid_id,
                "task_id": bid.task_id,
                "agent_id": bid.agent_id,
                "price": bid.price,
            })

    def get_bids(self, task_id: str) -> list[Bid]:
        """Get all bids for a task."""
        return self._bids.get(task_id, [])

    def get_pending_bids(self, task_id: str) -> list[Bid]:
        """Get pending bids for a task."""
        return [b for b in self._bids.get(task_id, []) if b.status == BidStatus.PENDING]

    def get_agent_bids(self, agent_id: str) -> list[Bid]:
        """Get all bids by an agent."""
        bids = []
        for task_bids in self._bids.values():
            bids.extend([b for b in task_bids if b.agent_id == agent_id])
        return bids

    async def update_bid_status(
        self, bid_id: str, task_id: str, status: BidStatus
    ) -> None:
        """Update a bid's status."""
        async with self._lock:
            for bid in self._bids.get(task_id, []):
                if bid.bid_id == bid_id:
                    bid.status = status
                    bid.resolved_at = datetime.utcnow()
                    self._log_event("bid_status_changed", {
                        "bid_id": bid_id,
                        "status": status.value,
                    })
                    break

    # -------------------------------------------------------------------------
    # Execution Management
    # -------------------------------------------------------------------------

    async def create_execution(self, execution: Execution) -> str:
        """Create an execution record."""
        async with self._lock:
            self._executions[execution.execution_id] = execution
            self._log_event("execution_created", {
                "execution_id": execution.execution_id,
                "task_id": execution.task_id,
                "agent_id": execution.agent_id,
            })
        return execution.execution_id

    async def get_execution(self, execution_id: str) -> Execution | None:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    def get_all_executions(self) -> list[Execution]:
        """Get all executions."""
        return list(self._executions.values())

    def get_task_execution(self, task_id: str) -> Execution | None:
        """Get the execution for a task."""
        for e in self._executions.values():
            if e.task_id == task_id:
                return e
        return None

    def get_agent_executions(self, agent_id: str) -> list[Execution]:
        """Get all executions by an agent."""
        return [e for e in self._executions.values() if e.agent_id == agent_id]

    async def update_execution(self, execution: Execution) -> None:
        """Update an execution record."""
        async with self._lock:
            self._executions[execution.execution_id] = execution
            self._log_event("execution_updated", {
                "execution_id": execution.execution_id,
                "status": execution.status.value,
            })

    async def complete_execution(
        self, execution_id: str, status: ExecutionStatus
    ) -> None:
        """Mark an execution as complete."""
        async with self._lock:
            if execution_id in self._executions:
                execution = self._executions[execution_id]
                execution.status = status
                execution.completed_at = datetime.utcnow()
                self._log_event("execution_completed", {
                    "execution_id": execution_id,
                    "status": status.value,
                })

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    def subscribe(
        self, capabilities: list[str], callback: Callable[[Task], Any]
    ) -> str:
        """Subscribe to tasks matching capabilities."""
        sub_id = f"sub_{len(self._subscriptions)}"
        if not capabilities:
            self._global_subscriptions.append(callback)
        else:
            for cap in capabilities:
                self._subscriptions[cap].append(callback)
        return sub_id

    async def _notify_subscribers(self, task: Task) -> None:
        """Notify subscribers about a new task."""
        notified = set()

        # Notify capability-specific subscribers
        for cap in task.specification.required_capabilities:
            for callback in self._subscriptions.get(cap, []):
                if id(callback) not in notified:
                    notified.add(id(callback))
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(task)
                        else:
                            callback(task)
                    except Exception as e:
                        self._log_event("subscription_error", {"error": str(e)})

        # Notify global subscribers
        for callback in self._global_subscriptions:
            if id(callback) not in notified:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(task)
                    else:
                        callback(task)
                except Exception as e:
                    self._log_event("subscription_error", {"error": str(e)})

    # -------------------------------------------------------------------------
    # Event Logging & Stats
    # -------------------------------------------------------------------------

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Log an event for analysis."""
        self._event_log.append({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        })

    def get_event_log(self) -> list[dict[str, Any]]:
        """Get the event log."""
        return self._event_log.copy()

    def get_stats(self) -> dict[str, Any]:
        """Get marketplace statistics."""
        tasks = self.get_all_tasks()
        executions = self.get_all_executions()

        completed = [e for e in executions if e.status == ExecutionStatus.COMPLETED]
        failed = [e for e in executions if e.status == ExecutionStatus.FAILED]

        total_value = sum(e.agreed_price for e in completed)

        return {
            "agents": {
                "total": len(self._agents),
                "online": len(self.get_online_agents()),
            },
            "tasks": {
                "total": len(tasks),
                "open": len([t for t in tasks if t.status == TaskStatus.OPEN]),
                "completed": len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
                "failed": len([t for t in tasks if t.status == TaskStatus.FAILED]),
            },
            "executions": {
                "total": len(executions),
                "completed": len(completed),
                "failed": len(failed),
                "in_progress": len([e for e in executions if e.is_active]),
            },
            "bids": {
                "total": sum(len(b) for b in self._bids.values()),
            },
            "economics": {
                "total_transacted": total_value,
                "average_price": total_value / len(completed) if completed else 0,
            },
            "events": len(self._event_log),
        }
