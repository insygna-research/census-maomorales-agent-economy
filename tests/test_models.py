"""Tests for data models."""

import pytest
from datetime import datetime, timedelta

from economy.models import (
    AgentProfile,
    AutonomyLevel,
    Capability,
    PricingModel,
    Task,
    TaskSpec,
    Budget,
    AllocationMethod,
    TaskStatus,
    Bid,
    BidStatus,
    Execution,
    ExecutionStatus,
)


class TestAgentProfile:
    def test_create_agent(self):
        agent = AgentProfile(
            agent_id="test-agent-1",
            name="TestBot",
            capabilities=[Capability(name="coding", skill_level=0.8)],
        )
        assert agent.agent_id == "test-agent-1"
        assert agent.name == "TestBot"
        assert len(agent.capabilities) == 1

    def test_has_capability(self):
        agent = AgentProfile(
            agent_id="test-agent-1",
            name="TestBot",
            capabilities=[
                Capability(name="coding"),
                Capability(name="writing"),
            ],
        )
        assert agent.has_capability("coding")
        assert agent.has_capability("writing")
        assert not agent.has_capability("research")

    def test_capability_names(self):
        agent = AgentProfile(
            agent_id="test-agent-1",
            name="TestBot",
            capabilities=[
                Capability(name="coding"),
                Capability(name="writing"),
            ],
        )
        assert agent.capability_names == ["coding", "writing"]

    def test_is_human_backed(self):
        autonomous = AgentProfile(
            agent_id="a1",
            name="Auto",
            autonomy_level=AutonomyLevel.FULL,
        )
        human = AgentProfile(
            agent_id="a2",
            name="Human",
            autonomy_level=AutonomyLevel.HUMAN_REQUIRED,
        )
        assert not autonomous.is_human_backed
        assert human.is_human_backed


class TestTask:
    def test_create_task(self):
        task = Task(
            task_id="task-1",
            publisher_id="user-1",
            specification=TaskSpec(
                title="Test Task",
                description="A test task",
            ),
            budget=Budget(min_price=1.0, max_price=10.0),
        )
        assert task.task_id == "task-1"
        assert task.specification.title == "Test Task"
        assert task.budget.max_price == 10.0

    def test_budget_acceptable(self):
        budget = Budget(min_price=5.0, max_price=10.0)
        assert not budget.is_acceptable(4.0)
        assert budget.is_acceptable(5.0)
        assert budget.is_acceptable(7.5)
        assert budget.is_acceptable(10.0)
        assert not budget.is_acceptable(11.0)

    def test_task_is_open(self):
        task = Task(
            task_id="task-1",
            publisher_id="user-1",
            specification=TaskSpec(title="Test", description="Test"),
            budget=Budget(max_price=10.0),
            status=TaskStatus.OPEN,
        )
        assert task.is_open
        task.status = TaskStatus.ASSIGNED
        assert not task.is_open

    def test_auction_ends_at(self):
        task = Task(
            task_id="task-1",
            publisher_id="user-1",
            specification=TaskSpec(title="Test", description="Test"),
            budget=Budget(max_price=10.0),
            auction_duration=timedelta(minutes=5),
        )
        # Not published yet
        assert task.auction_ends_at is None

        # After publishing
        task.published_at = datetime.utcnow()
        assert task.auction_ends_at is not None
        assert task.auction_ends_at > task.published_at


class TestBid:
    def test_create_bid(self):
        bid = Bid(
            bid_id="bid-1",
            task_id="task-1",
            agent_id="agent-1",
            price=5.0,
        )
        assert bid.bid_id == "bid-1"
        assert bid.price == 5.0
        assert bid.is_pending

    def test_bid_status(self):
        bid = Bid(
            bid_id="bid-1",
            task_id="task-1",
            agent_id="agent-1",
            price=5.0,
        )
        assert bid.is_pending
        assert not bid.is_won

        bid.status = BidStatus.ACCEPTED
        assert not bid.is_pending
        assert bid.is_won


class TestExecution:
    def test_create_execution(self):
        execution = Execution(
            execution_id="exec-1",
            task_id="task-1",
            agent_id="agent-1",
            bid_id="bid-1",
            agreed_price=5.0,
        )
        assert execution.execution_id == "exec-1"
        assert execution.is_active
        assert not execution.is_complete

    def test_execution_lifecycle(self):
        execution = Execution(
            execution_id="exec-1",
            task_id="task-1",
            agent_id="agent-1",
            bid_id="bid-1",
            agreed_price=5.0,
        )
        assert execution.status == ExecutionStatus.ASSIGNED
        assert execution.is_active

        execution.status = ExecutionStatus.IN_PROGRESS
        assert execution.is_active

        execution.status = ExecutionStatus.COMPLETED
        assert execution.is_complete
        assert execution.is_success

    def test_execution_duration(self):
        now = datetime.utcnow()
        execution = Execution(
            execution_id="exec-1",
            task_id="task-1",
            agent_id="agent-1",
            bid_id="bid-1",
            agreed_price=5.0,
            started_at=now,
            completed_at=now + timedelta(minutes=5),
        )
        assert execution.duration == timedelta(minutes=5)
