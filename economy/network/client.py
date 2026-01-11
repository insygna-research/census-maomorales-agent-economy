"""Market client for agents to connect to the marketplace."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Callable

import httpx
import websockets
from websockets.client import WebSocketClientProtocol

from economy.models import (
    AgentProfile,
    Bid,
    Execution,
    Task,
    ReputationSummary,
)
from economy.network.protocol import Message, MessageType


class MarketClient:
    """
    Client for agents to interact with the marketplace.

    Provides both HTTP REST API and WebSocket for real-time updates.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        agent_id: str | None = None,
    ) -> None:
        """
        Initialize the market client.

        Args:
            server_url: Base URL of the market server
            agent_id: Optional agent ID (required for some operations)
        """
        self.server_url = server_url.rstrip("/")
        self.ws_url = self.server_url.replace("http", "ws") + "/ws"
        self.agent_id = agent_id
        self._http_client: httpx.AsyncClient | None = None
        self._ws: WebSocketClientProtocol | None = None
        self._ws_task: asyncio.Task | None = None
        self._message_handlers: dict[MessageType, list[Callable]] = {}
        self._running = False

    async def __aenter__(self) -> "MarketClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    @property
    def http(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=30.0,
            )
        return self._http_client

    async def connect(self) -> None:
        """Connect to the market server."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=30.0,
            )

    async def disconnect(self) -> None:
        """Disconnect from the market server."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        if self._http_client:
            await self._http_client.aclose()

    # -------------------------------------------------------------------------
    # WebSocket Connection
    # -------------------------------------------------------------------------

    async def connect_websocket(self) -> None:
        """Connect via WebSocket for real-time updates."""
        if not self.agent_id:
            raise ValueError("agent_id required for WebSocket connection")

        self._ws = await websockets.connect(f"{self.ws_url}/{self.agent_id}")
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_listener())

    async def _ws_listener(self) -> None:
        """Listen for WebSocket messages."""
        while self._running and self._ws:
            try:
                data = await self._ws.recv()
                message = Message.from_dict(json.loads(data))
                await self._handle_message(message)
            except websockets.ConnectionClosed:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")

    async def _handle_message(self, message: Message) -> None:
        """Handle an incoming message."""
        handlers = self._message_handlers.get(message.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                print(f"Handler error: {e}")

    def on_message(self, message_type: MessageType, handler: Callable) -> None:
        """Register a message handler."""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    async def subscribe(self, capabilities: list[str]) -> None:
        """Subscribe to tasks with specific capabilities."""
        if self._ws:
            await self._ws.send(
                json.dumps(
                    Message(
                        type=MessageType.SUBSCRIBE,
                        payload={"capabilities": capabilities},
                    ).to_dict()
                )
            )

    async def send_heartbeat(self) -> None:
        """Send a heartbeat via WebSocket."""
        if self._ws:
            await self._ws.send(
                json.dumps(
                    Message(type=MessageType.AGENT_HEARTBEAT).to_dict()
                )
            )

    # -------------------------------------------------------------------------
    # Agent Management
    # -------------------------------------------------------------------------

    async def register(
        self,
        name: str,
        capabilities: list[str],
        description: str = "",
        autonomy_level: str = "full",
        base_rate: float = 1.0,
    ) -> AgentProfile:
        """Register a new agent."""
        response = await self.http.post(
            "/agents/register",
            json={
                "name": name,
                "description": description,
                "capabilities": capabilities,
                "autonomy_level": autonomy_level,
                "base_rate": base_rate,
            },
        )
        response.raise_for_status()
        data = response.json()
        self.agent_id = data["agent_id"]
        return AgentProfile.model_validate(data["profile"])

    async def heartbeat(self) -> None:
        """Send a heartbeat to the server."""
        if self.agent_id:
            await self.http.post(f"/agents/{self.agent_id}/heartbeat")

    async def get_agent(self, agent_id: str) -> AgentProfile:
        """Get an agent's profile."""
        response = await self.http.get(f"/agents/{agent_id}")
        response.raise_for_status()
        return AgentProfile.model_validate(response.json())

    async def get_reputation(self, agent_id: str | None = None) -> ReputationSummary:
        """Get reputation summary."""
        agent_id = agent_id or self.agent_id
        response = await self.http.get(f"/agents/{agent_id}/reputation")
        response.raise_for_status()
        return ReputationSummary.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------

    async def publish_task(
        self,
        title: str,
        description: str,
        budget_max: float,
        required_capabilities: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
        budget_min: float = 0.0,
        deadline_minutes: int | None = None,
        auction_duration_minutes: int = 5,
        allocation_method: str = "first_price",
    ) -> Task:
        """Publish a task to the marketplace."""
        response = await self.http.post(
            "/tasks/publish",
            json={
                "title": title,
                "description": description,
                "required_capabilities": required_capabilities or [],
                "inputs": inputs or {},
                "budget_min": budget_min,
                "budget_max": budget_max,
                "deadline_minutes": deadline_minutes,
                "auction_duration_minutes": auction_duration_minutes,
                "allocation_method": allocation_method,
            },
        )
        response.raise_for_status()
        return Task.model_validate(response.json()["task"])

    async def get_tasks(self, status: str | None = None) -> list[Task]:
        """Get all tasks, optionally filtered by status."""
        params = {}
        if status:
            params["status"] = status
        response = await self.http.get("/tasks", params=params)
        response.raise_for_status()
        return [Task.model_validate(t) for t in response.json()]

    async def get_open_tasks(self) -> list[Task]:
        """Get all open tasks."""
        response = await self.http.get("/tasks/open")
        response.raise_for_status()
        return [Task.model_validate(t) for t in response.json()]

    async def get_task(self, task_id: str) -> Task:
        """Get a specific task."""
        response = await self.http.get(f"/tasks/{task_id}")
        response.raise_for_status()
        return Task.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Bidding
    # -------------------------------------------------------------------------

    async def submit_bid(
        self,
        task_id: str,
        price: float,
        estimated_minutes: int = 60,
        confidence: float = 0.8,
        proposed_approach: str | None = None,
    ) -> Bid:
        """Submit a bid for a task."""
        if not self.agent_id:
            raise ValueError("agent_id required to submit bids")

        response = await self.http.post(
            "/bids/submit",
            json={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "price": price,
                "estimated_minutes": estimated_minutes,
                "confidence": confidence,
                "proposed_approach": proposed_approach,
            },
        )
        response.raise_for_status()
        return Bid.model_validate(response.json()["bid"])

    async def get_my_bids(self) -> list[Bid]:
        """Get all bids by this agent."""
        if not self.agent_id:
            raise ValueError("agent_id required")
        response = await self.http.get(f"/bids/agent/{self.agent_id}")
        response.raise_for_status()
        return [Bid.model_validate(b) for b in response.json()]

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    async def start_execution(self, execution_id: str) -> None:
        """Mark an execution as started."""
        response = await self.http.post(f"/executions/{execution_id}/start")
        response.raise_for_status()

    async def complete_execution(
        self,
        execution_id: str,
        output: Any,
        output_type: str = "text",
        execution_log: list[str] | None = None,
    ) -> None:
        """Mark an execution as complete."""
        response = await self.http.post(
            f"/executions/{execution_id}/complete",
            json={
                "execution_id": execution_id,
                "output": output,
                "output_type": output_type,
                "execution_log": execution_log or [],
            },
        )
        response.raise_for_status()

    async def fail_execution(self, execution_id: str, reason: str = "") -> None:
        """Mark an execution as failed."""
        response = await self.http.post(
            f"/executions/{execution_id}/fail",
            params={"reason": reason},
        )
        response.raise_for_status()

    async def get_execution(self, execution_id: str) -> Execution:
        """Get an execution by ID."""
        response = await self.http.get(f"/executions/{execution_id}")
        response.raise_for_status()
        return Execution.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Get marketplace statistics."""
        response = await self.http.get("/stats")
        response.raise_for_status()
        return response.json()

    async def get_leaderboard(self, limit: int = 10) -> list[ReputationSummary]:
        """Get reputation leaderboard."""
        response = await self.http.get(
            "/reputation/leaderboard", params={"limit": limit}
        )
        response.raise_for_status()
        return [ReputationSummary.model_validate(s) for s in response.json()]


class PollingMarketClient(MarketClient):
    """
    Market client that uses polling instead of WebSocket.

    Useful for simpler integrations or when WebSocket isn't available.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        agent_id: str | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        super().__init__(server_url, agent_id)
        self.poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None
        self._last_task_ids: set[str] = set()
        self._task_callbacks: list[Callable[[Task], Any]] = []

    def on_new_task(self, callback: Callable[[Task], Any]) -> None:
        """Register a callback for new tasks."""
        self._task_callbacks.append(callback)

    async def start_polling(self, capabilities: list[str] | None = None) -> None:
        """Start polling for new tasks."""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(capabilities))

    async def stop_polling(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()

    async def _poll_loop(self, capabilities: list[str] | None) -> None:
        """Polling loop."""
        while self._running:
            try:
                tasks = await self.get_open_tasks()
                for task in tasks:
                    if task.task_id not in self._last_task_ids:
                        # Check capability match
                        if capabilities:
                            task_caps = set(task.specification.required_capabilities)
                            if not task_caps or task_caps & set(capabilities):
                                await self._notify_task(task)
                        else:
                            await self._notify_task(task)
                        self._last_task_ids.add(task.task_id)

                # Send heartbeat
                await self.heartbeat()

            except Exception as e:
                print(f"Polling error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _notify_task(self, task: Task) -> None:
        """Notify callbacks about a new task."""
        for callback in self._task_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(task)
                else:
                    callback(task)
            except Exception as e:
                print(f"Callback error: {e}")
