"""Base agent class."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from rich.console import Console

from economy.models import (
    AgentProfile,
    Bid,
    Execution,
    ExecutionResult,
    Task,
)
from economy.network.client import MarketClient, PollingMarketClient
from economy.network.protocol import Message, MessageType


console = Console()


class BaseAgent(ABC):
    """
    Base class for all agents in the economy.

    Provides the core loop: discover tasks, decide to bid, execute if won.
    Subclasses implement the decision-making and execution logic.
    """

    def __init__(
        self,
        name: str,
        capabilities: list[str],
        server_url: str = "http://localhost:8000",
        description: str = "",
        base_rate: float = 1.0,
        autonomy_level: str = "full",
    ) -> None:
        """
        Initialize the agent.

        Args:
            name: Human-readable agent name
            capabilities: List of capability names
            server_url: Market server URL
            description: Agent description
            base_rate: Base pricing rate
            autonomy_level: Level of autonomy
        """
        self.name = name
        self.capabilities = capabilities
        self.description = description
        self.base_rate = base_rate
        self.autonomy_level = autonomy_level

        self.client = PollingMarketClient(server_url=server_url)
        self.profile: AgentProfile | None = None
        self._running = False
        self._active_executions: dict[str, Execution] = {}

    @property
    def agent_id(self) -> str | None:
        """Get the agent's ID."""
        return self.client.agent_id

    async def start(self) -> None:
        """Start the agent."""
        console.print(f"[bold blue]Starting agent: {self.name}[/bold blue]")

        # Connect to market
        await self.client.connect()

        # Register with the market
        self.profile = await self.client.register(
            name=self.name,
            capabilities=self.capabilities,
            description=self.description,
            autonomy_level=self.autonomy_level,
            base_rate=self.base_rate,
        )
        console.print(f"[green]Registered as {self.profile.agent_id}[/green]")

        # Set up task handler
        self.client.on_new_task(self._on_task_available)

        # Start polling
        self._running = True
        await self.client.start_polling(self.capabilities)

        console.print(f"[green]Agent {self.name} is running![/green]")

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        await self.client.stop_polling()
        await self.client.disconnect()
        console.print(f"[yellow]Agent {self.name} stopped[/yellow]")

    async def run(self) -> None:
        """Run the agent until interrupted."""
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def _on_task_available(self, task: Task) -> None:
        """Handle a new task being available."""
        console.print(f"[cyan]New task: {task.specification.title}[/cyan]")

        # Decide whether to bid
        if await self.should_bid(task):
            bid = await self.compute_bid(task)
            if bid:
                try:
                    submitted_bid = await self.client.submit_bid(
                        task_id=task.task_id,
                        price=bid["price"],
                        estimated_minutes=bid.get("estimated_minutes", 60),
                        confidence=bid.get("confidence", 0.8),
                        proposed_approach=bid.get("approach"),
                    )
                    console.print(
                        f"[green]Submitted bid: ${bid['price']:.2f} for {task.specification.title}[/green]"
                    )
                    
                    # Start checking if we won
                    asyncio.create_task(self._check_bid_result(task, submitted_bid))
                except Exception as e:
                    console.print(f"[red]Failed to submit bid: {e}[/red]")

    async def _check_bid_result(self, task: Task, bid: Bid) -> None:
        """Check if our bid won and execute if so."""
        # Wait for auction to end
        if task.auction_ends_at:
            wait_time = (task.auction_ends_at - datetime.utcnow()).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time + 2)  # Buffer

        # Check task status
        try:
            updated_task = await self.client.get_task(task.task_id)
            if updated_task.assigned_agent_id == self.agent_id:
                console.print(f"[bold green]Won task: {task.specification.title}![/bold green]")
                
                # Get execution
                executions = await self.client.http.get(f"/executions")
                for exec_data in executions.json():
                    if exec_data["task_id"] == task.task_id:
                        execution = Execution.model_validate(exec_data)
                        await self._execute_task(task, execution)
                        break
        except Exception as e:
            console.print(f"[red]Error checking bid result: {e}[/red]")

    async def _execute_task(self, task: Task, execution: Execution) -> None:
        """Execute a won task."""
        console.print(f"[blue]Executing: {task.specification.title}[/blue]")

        try:
            # Mark as started
            await self.client.start_execution(execution.execution_id)

            # Execute
            result = await self.execute(task)

            # Report completion
            await self.client.complete_execution(
                execution_id=execution.execution_id,
                output=result.output,
                output_type=result.output_type,
                execution_log=result.execution_log,
            )
            console.print(f"[bold green]Completed: {task.specification.title}[/bold green]")

        except Exception as e:
            console.print(f"[red]Execution failed: {e}[/red]")
            await self.client.fail_execution(
                execution_id=execution.execution_id,
                reason=str(e),
            )

    # -------------------------------------------------------------------------
    # Abstract methods for subclasses
    # -------------------------------------------------------------------------

    @abstractmethod
    async def should_bid(self, task: Task) -> bool:
        """
        Decide whether to bid on a task.

        Args:
            task: The available task

        Returns:
            True if agent should bid
        """
        pass

    @abstractmethod
    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """
        Compute bid parameters for a task.

        Args:
            task: The task to bid on

        Returns:
            Dict with 'price', 'estimated_minutes', 'confidence', 'approach'
            or None to not bid
        """
        pass

    @abstractmethod
    async def execute(self, task: Task) -> ExecutionResult:
        """
        Execute a task.

        Args:
            task: The task to execute

        Returns:
            ExecutionResult with output
        """
        pass


class SimpleAgent(BaseAgent):
    """
    Simple agent that bids on everything and returns mock results.

    Useful for testing and as a baseline.
    """

    async def should_bid(self, task: Task) -> bool:
        """Always bid if we have the capability."""
        if not task.specification.required_capabilities:
            return True
        return any(
            cap in self.capabilities
            for cap in task.specification.required_capabilities
        )

    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """Bid at 80% of max budget."""
        return {
            "price": task.budget.max_price * 0.8,
            "estimated_minutes": 30,
            "confidence": 0.7,
            "approach": "Standard execution",
        }

    async def execute(self, task: Task) -> ExecutionResult:
        """Return a mock result."""
        await asyncio.sleep(1)  # Simulate work
        return ExecutionResult(
            output=f"Completed task: {task.specification.title}",
            output_type="text",
            execution_log=["Started", "Processing", "Completed"],
            actual_duration=timedelta(seconds=1),
        )
