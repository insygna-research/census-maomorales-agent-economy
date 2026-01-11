"""Autonomous LLM-powered agent."""

import asyncio
from datetime import timedelta
from typing import Any

from rich.console import Console

from economy.models import ExecutionResult, Task
from economy.agents.base import BaseAgent

console = Console()


class AutonomousAgent(BaseAgent):
    """
    Fully autonomous agent powered by an LLM.

    Uses litellm for LLM abstraction, supporting multiple providers.
    """

    def __init__(
        self,
        name: str,
        capabilities: list[str],
        model: str = "gpt-4o-mini",
        server_url: str = "http://localhost:8000",
        description: str = "",
        base_rate: float = 1.0,
        system_prompt: str | None = None,
        max_bid_ratio: float = 0.85,  # Bid at most 85% of budget
        min_confidence: float = 0.5,  # Minimum confidence to bid
    ) -> None:
        """
        Initialize the autonomous agent.

        Args:
            name: Agent name
            capabilities: List of capabilities
            model: LLM model to use (e.g., 'gpt-4o-mini', 'claude-3-haiku-20240307')
            server_url: Market server URL
            description: Agent description
            base_rate: Base pricing rate
            system_prompt: Custom system prompt for the LLM
            max_bid_ratio: Maximum ratio of budget to bid
            min_confidence: Minimum confidence to place a bid
        """
        super().__init__(
            name=name,
            capabilities=capabilities,
            server_url=server_url,
            description=description or f"Autonomous agent powered by {model}",
            base_rate=base_rate,
            autonomy_level="full",
        )
        self.model = model
        self.max_bid_ratio = max_bid_ratio
        self.min_confidence = min_confidence
        self.system_prompt = system_prompt or self._default_system_prompt()

        self._llm_available = False
        self._check_llm()

    def _check_llm(self) -> None:
        """Check if LLM is available."""
        try:
            import litellm
            self._llm_available = True
        except ImportError:
            console.print("[yellow]litellm not available, using mock responses[/yellow]")
            self._llm_available = False

    def _default_system_prompt(self) -> str:
        """Default system prompt for the agent."""
        return f"""You are {self.name}, an autonomous AI agent participating in a task marketplace.

Your capabilities: {', '.join(self.capabilities)}

When given a task, you should:
1. Analyze the requirements carefully
2. Execute the task to the best of your ability
3. Provide clear, well-structured output
4. Be honest about any limitations

Always aim for high-quality results."""

    async def _llm_complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """Get a completion from the LLM."""
        if not self._llm_available:
            # Mock response for testing
            return f"[Mock response for: {prompt[:100]}...]"

        import litellm

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            console.print(f"[red]LLM error: {e}[/red]")
            return f"Error: {e}"

    async def should_bid(self, task: Task) -> bool:
        """
        Decide whether to bid using LLM reasoning.

        Considers:
        - Capability match
        - Task complexity
        - Budget adequacy
        """
        # Quick capability check
        required_caps = task.specification.required_capabilities
        if required_caps:
            if not any(cap in self.capabilities for cap in required_caps):
                return False

        # For simple tasks, always bid
        if task.budget.max_price >= self.base_rate:
            return True

        # For complex decisions, use LLM
        if self._llm_available:
            prompt = f"""Should I bid on this task?

Task: {task.specification.title}
Description: {task.specification.description}
Required capabilities: {required_caps}
Budget: ${task.budget.min_price} - ${task.budget.max_price}

My capabilities: {self.capabilities}
My base rate: ${self.base_rate}

Respond with just YES or NO and a brief reason."""

            response = await self._llm_complete(prompt, max_tokens=100)
            return response.strip().upper().startswith("YES")

        return True

    async def compute_bid(self, task: Task) -> dict[str, Any] | None:
        """
        Compute bid parameters using LLM estimation.
        """
        # Base price calculation
        price = min(
            task.budget.max_price * self.max_bid_ratio,
            self.base_rate * 2,  # Don't go too low
        )

        # Estimate time based on description length and complexity
        desc_length = len(task.specification.description)
        estimated_minutes = max(15, min(desc_length // 10, 120))

        # Confidence based on capability match
        required_caps = set(task.specification.required_capabilities)
        my_caps = set(self.capabilities)
        if required_caps:
            overlap = len(required_caps & my_caps) / len(required_caps)
            confidence = 0.5 + 0.5 * overlap
        else:
            confidence = 0.7

        if confidence < self.min_confidence:
            return None

        return {
            "price": price,
            "estimated_minutes": estimated_minutes,
            "confidence": confidence,
            "approach": f"Will use {self.model} to complete this task",
        }

    async def execute(self, task: Task) -> ExecutionResult:
        """
        Execute the task using LLM.
        """
        console.print(f"[blue]Executing with {self.model}...[/blue]")

        execution_log = ["Starting task execution"]

        # Build the execution prompt
        prompt = f"""Complete the following task:

Title: {task.specification.title}
Description: {task.specification.description}

"""
        if task.specification.inputs:
            prompt += f"Inputs provided:\n"
            for key, value in task.specification.inputs.items():
                prompt += f"- {key}: {value}\n"

        prompt += f"""
Expected output format: {task.specification.expected_output_format}

Please provide your complete response."""

        execution_log.append("Sending to LLM")

        # Get LLM response
        start_time = asyncio.get_event_loop().time()
        output = await self._llm_complete(prompt, system=self.system_prompt)
        duration = asyncio.get_event_loop().time() - start_time

        execution_log.append(f"LLM responded in {duration:.1f}s")
        execution_log.append("Task completed")

        return ExecutionResult(
            output=output,
            output_type=task.specification.expected_output_format,
            execution_log=execution_log,
            actual_duration=timedelta(seconds=duration),
            metadata={
                "model": self.model,
                "prompt_length": len(prompt),
                "response_length": len(output),
            },
        )


class WebResearchAgent(AutonomousAgent):
    """
    Autonomous agent with web browsing capabilities.

    Can search the web to find information for tasks.
    """

    def __init__(
        self,
        name: str = "WebResearcher",
        model: str = "gpt-4o-mini",
        server_url: str = "http://localhost:8000",
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            capabilities=["web_search", "research", "summarization"],
            model=model,
            server_url=server_url,
            description="Agent that can search the web and synthesize information",
            **kwargs,
        )

    async def _web_search(self, query: str) -> list[dict]:
        """
        Perform a web search.

        This is a mock implementation. In production, you'd use
        a real search API like Serper, SerpAPI, or Brave Search.
        """
        console.print(f"[cyan]Searching web for: {query}[/cyan]")

        # Mock search results
        # In production, use httpx to call a search API
        return [
            {
                "title": f"Result 1 for '{query}'",
                "url": "https://example.com/1",
                "snippet": f"This is a relevant result about {query}...",
            },
            {
                "title": f"Result 2 for '{query}'",
                "url": "https://example.com/2",
                "snippet": f"Another perspective on {query}...",
            },
        ]

    async def execute(self, task: Task) -> ExecutionResult:
        """Execute task with web research capabilities."""
        execution_log = ["Starting web research task"]

        # Check if this is a search task
        description = task.specification.description.lower()
        inputs = task.specification.inputs

        search_query = inputs.get("query") or inputs.get("search_query")

        if not search_query and ("search" in description or "find" in description):
            # Extract query from description
            search_query = task.specification.title

        if search_query:
            execution_log.append(f"Searching for: {search_query}")
            results = await self._web_search(search_query)
            execution_log.append(f"Found {len(results)} results")

            # Synthesize results with LLM
            prompt = f"""Based on these search results, answer the question/task:

Task: {task.specification.title}
Description: {task.specification.description}

Search Results:
"""
            for i, r in enumerate(results, 1):
                prompt += f"\n{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n"

            prompt += "\nProvide a comprehensive answer based on these results."

            output = await self._llm_complete(prompt, system=self.system_prompt)
            execution_log.append("Synthesized results")

            return ExecutionResult(
                output=output,
                output_type="text",
                execution_log=execution_log,
                actual_duration=timedelta(seconds=5),
                metadata={
                    "search_query": search_query,
                    "results_count": len(results),
                },
            )

        # Fall back to standard execution
        return await super().execute(task)
