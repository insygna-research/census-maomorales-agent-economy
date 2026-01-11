"""Human-in-the-loop agent."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.markdown import Markdown

from economy.models import ExecutionResult, Task
from economy.agents.base import BaseAgent

console = Console()


class HumanBackedAgent(BaseAgent):
    """
    Agent that requires human involvement.

    Tasks are presented to the human via CLI, and they can:
    - Decide whether to bid
    - Set bid parameters
    - Execute the task manually or with AI assistance
    """

    def __init__(
        self,
        name: str,
        capabilities: list[str],
        server_url: str = "http://localhost:8000",
        description: str = "",
        base_rate: float = 5.0,  # Humans are more expensive
        auto_bid: bool = False,  # If True, auto-bid and wait for execution
        default_response_minutes: int = 60,
    ) -> None:
        """
        Initialize the human-backed agent.

        Args:
            name: Agent/human name
            capabilities: List of capabilities
            server_url: Market server URL
            description: Agent description
            base_rate: Base hourly rate
            auto_bid: Whether to automatically bid on matching tasks
            default_response_minutes: Default time estimate for bids
        """
        super().__init__(
            name=name,
            capabilities=capabilities,
            server_url=server_url,
            description=description or f"Human agent: {name}",
            base_rate=base_rate,
            autonomy_level="human_required",
        )
        self.auto_bid = auto_bid
        self.default_response_minutes = default_response_minutes
        self._pending_tasks: asyncio.Queue = asyncio.Queue()

    async def should_bid(self, task: Task) -> bool:
        """
        Ask the human whether to bid.
        """
        # Check capability match first
        required_caps = task.specification.required_capabilities
        if required_caps:
            if not any(cap in self.capabilities for cap in required_caps):
                return False

        if self.auto_bid:
            console.print(f"[cyan]Auto-bidding on: {task.specification.title}[/cyan]")
            return True

        # Show task to human
        console.print()
        console.print(Panel(
            f"""[bold]{task.specification.title}[/bold]

{task.specification.description}

[dim]Required: {', '.join(required_caps) or 'Any'}[/dim]
[dim]Budget: ${task.budget.min_price:.2f} - ${task.budget.max_price:.2f}[/dim]
[dim]Deadline: {task.deadline or 'None'}[/dim]""",
            title="📋 New Task Available",
            border_style="cyan",
        ))

        return Confirm.ask("Would you like to bid on this task?", default=True)

    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """
        Get bid parameters from human.
        """
        if self.auto_bid:
            return {
                "price": task.budget.max_price * 0.9,
                "estimated_minutes": self.default_response_minutes,
                "confidence": 0.9,
                "approach": "Human execution with expertise",
            }

        console.print("\n[bold]Set your bid:[/bold]")

        # Get price
        default_price = task.budget.max_price * 0.8
        price_str = Prompt.ask(
            "Price",
            default=f"{default_price:.2f}",
        )
        try:
            price = float(price_str)
        except ValueError:
            price = default_price

        # Get time estimate
        time_str = Prompt.ask(
            "Estimated minutes",
            default=str(self.default_response_minutes),
        )
        try:
            estimated_minutes = int(time_str)
        except ValueError:
            estimated_minutes = self.default_response_minutes

        # Get confidence
        confidence_str = Prompt.ask(
            "Confidence (0.0-1.0)",
            default="0.9",
        )
        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.9

        approach = Prompt.ask(
            "Brief approach description",
            default="Human expertise",
        )

        return {
            "price": price,
            "estimated_minutes": estimated_minutes,
            "confidence": confidence,
            "approach": approach,
        }

    async def execute(self, task: Task) -> ExecutionResult:
        """
        Execute task with human input.
        """
        console.print()
        console.print(Panel(
            f"""[bold]{task.specification.title}[/bold]

{task.specification.description}

[bold]Inputs:[/bold]
{self._format_inputs(task.specification.inputs)}

[dim]Please complete this task and provide your response below.[/dim]""",
            title="🎯 Task Assigned - Please Execute",
            border_style="green",
        ))

        execution_log = [f"Task presented to human at {datetime.utcnow().isoformat()}"]

        # Get human response
        console.print("\n[bold]Enter your response (end with an empty line):[/bold]")
        lines = []
        while True:
            line = Prompt.ask("", default="")
            if not line and lines:
                break
            lines.append(line)

        output = "\n".join(lines)
        execution_log.append(f"Human provided response at {datetime.utcnow().isoformat()}")

        # Ask for quality self-assessment
        quality_str = Prompt.ask(
            "Rate your confidence in this response (0.0-1.0)",
            default="0.8",
        )
        try:
            quality = float(quality_str)
        except ValueError:
            quality = 0.8

        return ExecutionResult(
            output=output,
            output_type=task.specification.expected_output_format,
            execution_log=execution_log,
            actual_duration=timedelta(minutes=5),  # Approximate
            metadata={
                "human_quality_rating": quality,
                "response_length": len(output),
            },
        )

    def _format_inputs(self, inputs: dict) -> str:
        """Format task inputs for display."""
        if not inputs:
            return "[dim]None[/dim]"
        lines = []
        for key, value in inputs.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            lines.append(f"  • {key}: {value}")
        return "\n".join(lines)


class SupervisedAgent(HumanBackedAgent):
    """
    Agent that uses AI for execution but requires human review.

    AI generates the response, human approves or modifies it.
    """

    def __init__(
        self,
        name: str,
        capabilities: list[str],
        model: str = "gpt-4o-mini",
        server_url: str = "http://localhost:8000",
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            capabilities=capabilities,
            server_url=server_url,
            **kwargs,
        )
        self.model = model
        self.autonomy_level = "supervised"
        self._llm_available = self._check_llm()

    def _check_llm(self) -> bool:
        """Check if LLM is available."""
        try:
            import litellm
            return True
        except ImportError:
            return False

    async def _llm_complete(self, prompt: str) -> str:
        """Get LLM completion."""
        if not self._llm_available:
            return "[LLM not available - please provide response manually]"

        import litellm
        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[LLM error: {e}]"

    async def execute(self, task: Task) -> ExecutionResult:
        """Execute with AI assistance and human review."""
        execution_log = ["Starting supervised execution"]

        # Generate AI response
        console.print("\n[cyan]Generating AI response...[/cyan]")

        prompt = f"""Complete this task:

Title: {task.specification.title}
Description: {task.specification.description}

Inputs: {task.specification.inputs}

Provide a complete response."""

        ai_response = await self._llm_complete(prompt)
        execution_log.append("AI generated initial response")

        # Show to human for review
        console.print()
        console.print(Panel(
            Markdown(ai_response),
            title="🤖 AI-Generated Response",
            border_style="blue",
        ))

        # Ask for approval
        action = Prompt.ask(
            "Action",
            choices=["approve", "edit", "reject"],
            default="approve",
        )

        if action == "approve":
            output = ai_response
            execution_log.append("Human approved AI response")
        elif action == "edit":
            console.print("\n[bold]Enter your edited response:[/bold]")
            lines = []
            while True:
                line = Prompt.ask("", default="")
                if not line and lines:
                    break
                lines.append(line)
            output = "\n".join(lines)
            execution_log.append("Human edited AI response")
        else:
            console.print("\n[bold]Enter your complete response:[/bold]")
            lines = []
            while True:
                line = Prompt.ask("", default="")
                if not line and lines:
                    break
                lines.append(line)
            output = "\n".join(lines)
            execution_log.append("Human rejected AI response and provided own")

        return ExecutionResult(
            output=output,
            output_type=task.specification.expected_output_format,
            execution_log=execution_log,
            actual_duration=timedelta(minutes=3),
            metadata={
                "ai_model": self.model,
                "human_action": action,
            },
        )
