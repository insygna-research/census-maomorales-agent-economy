"""Communication protocol for the agent economy."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages in the protocol."""

    # Registration
    AGENT_REGISTER = "agent_register"
    AGENT_REGISTERED = "agent_registered"
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_DEREGISTER = "agent_deregister"

    # Task lifecycle
    TASK_PUBLISHED = "task_published"
    TASK_UPDATED = "task_updated"
    TASK_CANCELLED = "task_cancelled"

    # Bidding
    BID_SUBMITTED = "bid_submitted"
    BID_ACCEPTED = "bid_accepted"
    BID_REJECTED = "bid_rejected"

    # Auction
    AUCTION_STARTED = "auction_started"
    AUCTION_CLOSED = "auction_closed"

    # Execution
    TASK_ASSIGNED = "task_assigned"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_PROGRESS = "execution_progress"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"

    # Evaluation
    EVALUATION_REQUESTED = "evaluation_requested"
    EVALUATION_SUBMITTED = "evaluation_submitted"

    # Queries
    GET_TASKS = "get_tasks"
    GET_AGENT = "get_agent"
    GET_REPUTATION = "get_reputation"
    GET_STATS = "get_stats"

    # Responses
    RESPONSE = "response"
    ERROR = "error"

    # Subscriptions
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class Message(BaseModel):
    """A message in the protocol."""

    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    sender_id: str | None = None
    message_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str | None = None  # For request-response pairing

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "payload": self.payload,
            "sender_id": self.sender_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create from dictionary."""
        return cls(
            type=MessageType(data["type"]),
            payload=data.get("payload", {}),
            sender_id=data.get("sender_id"),
            message_id=data.get("message_id"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.utcnow(),
            correlation_id=data.get("correlation_id"),
        )


# Convenience message builders
def task_published_message(task_dict: dict) -> Message:
    """Create a task published message."""
    return Message(type=MessageType.TASK_PUBLISHED, payload={"task": task_dict})


def bid_submitted_message(bid_dict: dict) -> Message:
    """Create a bid submitted message."""
    return Message(type=MessageType.BID_SUBMITTED, payload={"bid": bid_dict})


def task_assigned_message(
    task_id: str, agent_id: str, execution_id: str, price: float
) -> Message:
    """Create a task assigned message."""
    return Message(
        type=MessageType.TASK_ASSIGNED,
        payload={
            "task_id": task_id,
            "agent_id": agent_id,
            "execution_id": execution_id,
            "price": price,
        },
    )


def execution_completed_message(
    execution_id: str, task_id: str, result: dict
) -> Message:
    """Create an execution completed message."""
    return Message(
        type=MessageType.EXECUTION_COMPLETED,
        payload={
            "execution_id": execution_id,
            "task_id": task_id,
            "result": result,
        },
    )


def error_message(error: str, details: dict | None = None) -> Message:
    """Create an error message."""
    return Message(
        type=MessageType.ERROR,
        payload={"error": error, "details": details or {}},
    )
