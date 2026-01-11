"""Evaluators for assessing task execution quality."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from economy.models import Evaluation, ExecutionResult, Task


class Evaluator(ABC):
    """Base class for task evaluators."""

    name: str = "base"
    weight: float = 1.0

    @abstractmethod
    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        """
        Evaluate an execution result.

        Args:
            task: The original task
            result: The execution result

        Returns:
            Tuple of (score 0-1, feedback string)
        """
        pass


class CompletenessEvaluator(Evaluator):
    """Evaluates whether the output addresses all parts of the task."""

    name = "completeness"
    weight = 0.3

    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        output = str(result.output)

        # Basic completeness checks
        if not output or len(output.strip()) < 10:
            return 0.0, "Output is empty or too short"

        # Check if key terms from task are addressed
        description = task.specification.description.lower()
        output_lower = output.lower()

        # Extract key terms (simple approach)
        key_terms = [
            word for word in description.split()
            if len(word) > 4 and word.isalpha()
        ]

        if not key_terms:
            return 0.8, "Task has no clear key terms to check"

        matches = sum(1 for term in key_terms if term in output_lower)
        coverage = matches / len(key_terms)

        if coverage > 0.7:
            return 1.0, "Output addresses most key aspects of the task"
        elif coverage > 0.4:
            return 0.7, "Output addresses some aspects but may be incomplete"
        else:
            return 0.4, "Output may not fully address the task requirements"


class FormatEvaluator(Evaluator):
    """Evaluates whether the output matches expected format."""

    name = "format"
    weight = 0.2

    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        expected_format = task.specification.expected_output_format.lower()
        output = str(result.output)

        if expected_format == "text":
            if len(output) > 20:
                return 1.0, "Valid text output"
            return 0.5, "Text output is very short"

        elif expected_format == "json":
            import json
            try:
                json.loads(output)
                return 1.0, "Valid JSON format"
            except json.JSONDecodeError:
                return 0.0, "Invalid JSON format"

        elif expected_format == "markdown":
            # Check for markdown indicators
            if any(
                indicator in output
                for indicator in ["#", "**", "```", "- ", "* "]
            ):
                return 1.0, "Contains markdown formatting"
            return 0.6, "May not use markdown formatting"

        elif expected_format == "code":
            # Check for code indicators
            if "```" in output or "def " in output or "function " in output:
                return 1.0, "Contains code"
            return 0.6, "May not contain code"

        else:
            # Unknown format, be lenient
            return 0.8, f"Format '{expected_format}' not specifically validated"


class LengthEvaluator(Evaluator):
    """Evaluates output length appropriateness."""

    name = "length"
    weight = 0.1

    def __init__(self, min_length: int = 50, ideal_length: int = 500) -> None:
        self.min_length = min_length
        self.ideal_length = ideal_length

    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        output = str(result.output)
        length = len(output)

        if length < self.min_length:
            score = length / self.min_length
            return score, f"Output too short ({length} chars)"

        if length > self.ideal_length * 3:
            return 0.8, f"Output may be excessively long ({length} chars)"

        return 1.0, f"Appropriate length ({length} chars)"


class LLMJudgeEvaluator(Evaluator):
    """Uses an LLM to judge output quality."""

    name = "llm_judge"
    weight = 0.4

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._llm_available = self._check_llm()

    def _check_llm(self) -> bool:
        try:
            import litellm
            return True
        except ImportError:
            return False

    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        if not self._llm_available:
            return 0.7, "LLM evaluation not available, using default score"

        import litellm

        prompt = f"""Evaluate this task completion on a scale of 0.0 to 1.0.

TASK:
Title: {task.specification.title}
Description: {task.specification.description}

OUTPUT:
{str(result.output)[:2000]}

Rate the output on:
1. Relevance to the task
2. Completeness
3. Quality and accuracy

Respond with ONLY a JSON object like:
{{"score": 0.85, "feedback": "Brief explanation"}}"""

        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            content = response.choices[0].message.content

            # Parse response
            import json
            import re

            # Try to extract JSON
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group())
                score = float(data.get("score", 0.5))
                feedback = data.get("feedback", "")
                return min(max(score, 0.0), 1.0), feedback

            return 0.5, "Could not parse LLM evaluation"

        except Exception as e:
            return 0.5, f"LLM evaluation error: {e}"


class CompositeEvaluator(Evaluator):
    """Combines multiple evaluators with weights."""

    name = "composite"

    def __init__(self, evaluators: list[Evaluator] | None = None) -> None:
        self.evaluators = evaluators or [
            CompletenessEvaluator(),
            FormatEvaluator(),
            LengthEvaluator(),
        ]

    async def evaluate(
        self, task: Task, result: ExecutionResult
    ) -> tuple[float, str]:
        scores = []
        feedbacks = []
        total_weight = 0

        for evaluator in self.evaluators:
            score, feedback = await evaluator.evaluate(task, result)
            scores.append((score, evaluator.weight))
            feedbacks.append(f"{evaluator.name}: {feedback}")
            total_weight += evaluator.weight

        # Weighted average
        if total_weight > 0:
            final_score = sum(s * w for s, w in scores) / total_weight
        else:
            final_score = sum(s for s, _ in scores) / len(scores) if scores else 0.5

        return final_score, " | ".join(feedbacks)

    async def evaluate_full(
        self, task: Task, result: ExecutionResult, execution_id: str
    ) -> Evaluation:
        """Produce a full Evaluation object."""
        from ulid import ULID

        criterion_scores = {}
        feedbacks = []

        for evaluator in self.evaluators:
            score, feedback = await evaluator.evaluate(task, result)
            criterion_scores[evaluator.name] = score
            feedbacks.append(f"{evaluator.name}: {feedback}")

        # Calculate overall score
        total_weight = sum(e.weight for e in self.evaluators)
        overall = sum(
            criterion_scores[e.name] * e.weight for e in self.evaluators
        ) / total_weight if total_weight > 0 else 0.5

        return Evaluation(
            evaluation_id=str(ULID()),
            execution_id=execution_id,
            evaluator_id="system",
            evaluator_type="automated",
            criterion_scores=criterion_scores,
            overall_score=overall,
            feedback=" | ".join(feedbacks),
            passed=overall >= 0.5,
        )
