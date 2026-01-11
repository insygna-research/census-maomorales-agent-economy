"""Manager agent that decomposes tasks and delegates to other agents."""

import asyncio
from datetime import timedelta
from typing import Any

from rich.console import Console

from economy.models import ExecutionResult, Task, TaskStatus
from economy.agents.base import BaseAgent

console = Console()


class ManagerAgent(BaseAgent):
    """
    Agent that decomposes complex tasks and delegates to other agents.

    This agent acts as a contractor:
    1. Takes on complex tasks
    2. Breaks them into subtasks
    3. Publishes subtasks to the market
    4. Aggregates results
    """

    def __init__(
        self,
        name: str = "TaskManager",
        server_url: str = "http://localhost:8000",
        model: str = "gpt-4o-mini",
        markup: float = 0.2,  # 20% markup on subtasks
        max_subtasks: int = 5,
        **kwargs,
    ) -> None:
        """
        Initialize the manager agent.

        Args:
            name: Agent name
            server_url: Market server URL
            model: LLM model for decomposition
            markup: Markup percentage on subtask costs
            max_subtasks: Maximum number of subtasks to create
        """
        super().__init__(
            name=name,
            capabilities=["task_management", "decomposition", "coordination"],
            server_url=server_url,
            description="Manager agent that decomposes and coordinates complex tasks",
            autonomy_level="full",
            **kwargs,
        )
        self.model = model
        self.markup = markup
        self.max_subtasks = max_subtasks
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
            return "subtask1: Complete the first part\nsubtask2: Complete the second part"

        import litellm
        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            return response.choices[0].message.content
        except Exception as e:
            console.print(f"[red]LLM error: {e}[/red]")
            return ""

    async def should_bid(self, task: Task) -> bool:
        """
        Bid on complex tasks that can be decomposed.
        """
        # Don't bid on our own subtasks
        if task.parent_task_id:
            return False

        # Only bid on tasks that seem complex enough to decompose
        description = task.specification.description
        if len(description) < 100:
            return False

        # Check if budget allows for decomposition
        if task.budget.max_price < 5.0:  # Need budget for multiple subtasks
            return False

        return True

    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """
        Compute bid based on estimated decomposition.
        """
        # Estimate we'll use 80% of budget for subtasks, keep 20% margin
        price = task.budget.max_price * 0.95

        return {
            "price": price,
            "estimated_minutes": 30,  # Coordination time
            "confidence": 0.75,
            "approach": "Will decompose into subtasks and coordinate execution",
        }

    async def _decompose_task(self, task: Task) -> list[dict]:
        """
        Use LLM to decompose task into subtasks.
        """
        prompt = f"""Decompose this task into {self.max_subtasks} or fewer subtasks.

Task: {task.specification.title}
Description: {task.specification.description}

For each subtask, provide:
1. A clear title
2. A detailed description
3. Required capability (one of: coding, research, writing, analysis, review)
4. Estimated budget as percentage of total

Format each subtask as:
SUBTASK: <title>
DESCRIPTION: <description>
CAPABILITY: <capability>
BUDGET_PERCENT: <percentage>

---"""

        response = await self._llm_complete(prompt)

        # Parse subtasks
        subtasks = []
        current = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("SUBTASK:"):
                if current:
                    subtasks.append(current)
                current = {"title": line[8:].strip()}
            elif line.startswith("DESCRIPTION:"):
                current["description"] = line[12:].strip()
            elif line.startswith("CAPABILITY:"):
                current["capability"] = line[11:].strip().lower()
            elif line.startswith("BUDGET_PERCENT:"):
                try:
                    pct = float(line[15:].strip().replace("%", ""))
                    current["budget_percent"] = pct / 100
                except ValueError:
                    current["budget_percent"] = 1.0 / self.max_subtasks

        if current:
            subtasks.append(current)

        return subtasks[:self.max_subtasks]

    async def _allocate_budget(
        self, total_budget: float, subtasks: list[dict]
    ) -> list[float]:
        """
        Allocate budget across subtasks.
        """
        # Reserve margin for coordination
        available = total_budget * (1 - self.markup)

        budgets = []
        for subtask in subtasks:
            pct = subtask.get("budget_percent", 1.0 / len(subtasks))
            budgets.append(available * pct)

        return budgets

    async def execute(self, task: Task) -> ExecutionResult:
        """
        Execute by decomposing and delegating.
        """
        execution_log = ["Starting task decomposition"]

        console.print(f"[blue]Decomposing task: {task.specification.title}[/blue]")

        # Decompose the task
        subtasks = await self._decompose_task(task)
        execution_log.append(f"Decomposed into {len(subtasks)} subtasks")

        if not subtasks:
            return ExecutionResult(
                output="Failed to decompose task",
                output_type="text",
                execution_log=execution_log + ["Decomposition failed"],
                actual_duration=timedelta(seconds=10),
            )

        console.print(f"[cyan]Created {len(subtasks)} subtasks[/cyan]")

        # Allocate budget
        budgets = await self._allocate_budget(task.budget.max_price, subtasks)
        execution_log.append(f"Allocated budgets: {budgets}")

        # Publish subtasks
        subtask_ids = []
        for i, (subtask, budget) in enumerate(zip(subtasks, budgets)):
            console.print(f"  • Publishing: {subtask.get('title', f'Subtask {i+1}')}")

            try:
                published = await self.client.publish_task(
                    title=subtask.get("title", f"Subtask {i+1}"),
                    description=subtask.get("description", ""),
                    budget_max=budget,
                    required_capabilities=[subtask.get("capability", "general")],
                    auction_duration_minutes=2,  # Short auction for subtasks
                )
                subtask_ids.append(published.task_id)
                execution_log.append(f"Published subtask: {published.task_id}")
            except Exception as e:
                execution_log.append(f"Failed to publish subtask: {e}")
                console.print(f"[red]Failed to publish subtask: {e}[/red]")

        if not subtask_ids:
            return ExecutionResult(
                output="Failed to publish any subtasks",
                output_type="text",
                execution_log=execution_log,
                actual_duration=timedelta(seconds=30),
            )

        # Wait for subtasks to complete
        console.print("[cyan]Waiting for subtasks to complete...[/cyan]")
        results = await self._wait_for_subtasks(subtask_ids, timeout=300)
        execution_log.append(f"Collected {len(results)} results")

        # Aggregate results
        console.print("[blue]Aggregating results...[/blue]")
        final_output = await self._aggregate_results(task, subtasks, results)
        execution_log.append("Aggregated final result")

        return ExecutionResult(
            output=final_output,
            output_type=task.specification.expected_output_format,
            execution_log=execution_log,
            actual_duration=timedelta(minutes=5),
            metadata={
                "subtask_count": len(subtasks),
                "completed_count": len([r for r in results if r]),
                "subtask_ids": subtask_ids,
            },
        )

    async def _wait_for_subtasks(
        self, task_ids: list[str], timeout: int = 300
    ) -> list[str | None]:
        """
        Wait for subtasks to complete.
        """
        results = [None] * len(task_ids)
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            all_done = True

            for i, task_id in enumerate(task_ids):
                if results[i] is not None:
                    continue

                try:
                    task = await self.client.get_task(task_id)
                    if task.status == TaskStatus.COMPLETED:
                        # Get the execution result
                        exec_response = await self.client.http.get(f"/executions")
                        for exec_data in exec_response.json():
                            if exec_data["task_id"] == task_id:
                                if exec_data.get("result"):
                                    results[i] = exec_data["result"].get("output", "")
                                break
                        if results[i] is None:
                            results[i] = "[Completed but no output]"
                    elif task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                        results[i] = f"[{task.status.value}]"
                    else:
                        all_done = False
                except Exception as e:
                    console.print(f"[yellow]Error checking subtask: {e}[/yellow]")
                    all_done = False

            if all_done:
                break

            await asyncio.sleep(5)

        return results

    async def _aggregate_results(
        self,
        original_task: Task,
        subtasks: list[dict],
        results: list[str | None],
    ) -> str:
        """
        Aggregate subtask results into final output.
        """
        prompt = f"""Combine these subtask results into a final response.

Original task: {original_task.specification.title}
Original description: {original_task.specification.description}

Subtask results:
"""
        for i, (subtask, result) in enumerate(zip(subtasks, results)):
            prompt += f"""
--- Subtask {i+1}: {subtask.get('title', 'Unknown')} ---
{result or '[No result]'}
"""

        prompt += """

Provide a cohesive final response that integrates all subtask results."""

        return await self._llm_complete(prompt)
