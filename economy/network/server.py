"""Market server - HTTP API and WebSocket for the agent economy."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from ulid import ULID

from economy.models import (
    AgentProfile,
    AllocationMethod,
    Bid,
    BidStatus,
    Budget,
    Execution,
    ExecutionResult,
    ExecutionStatus,
    Task,
    TaskSpec,
    TaskStatus,
)
from economy.market.board import TaskBoard
from economy.market.auctions import AuctionEngine, AuctionScheduler
from economy.market.allocation import TaskAllocator
from economy.reputation.ledger import ReputationLedger
from economy.network.protocol import Message, MessageType


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class PublishTaskRequest(BaseModel):
    """Request to publish a task."""

    title: str
    description: str
    required_capabilities: list[str] = []
    inputs: dict[str, Any] = {}
    budget_min: float = 0.0
    budget_max: float
    deadline_minutes: int | None = None
    auction_duration_minutes: int = 5
    allocation_method: str = "first_price"


class SubmitBidRequest(BaseModel):
    """Request to submit a bid."""

    task_id: str
    agent_id: str
    price: float
    estimated_minutes: int = 60
    confidence: float = 0.8
    proposed_approach: str | None = None


class CompleteExecutionRequest(BaseModel):
    """Request to mark execution complete."""

    execution_id: str
    output: Any
    output_type: str = "text"
    execution_log: list[str] = []


class RegisterAgentRequest(BaseModel):
    """Request to register an agent."""

    name: str
    description: str = ""
    capabilities: list[str] = []
    autonomy_level: str = "full"
    base_rate: float = 1.0


# -------------------------------------------------------------------------
# Connection Manager for WebSockets
# -------------------------------------------------------------------------


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.subscriptions: dict[str, set[str]] = {}  # agent_id -> capability set

    async def connect(self, agent_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[agent_id] = websocket

    def disconnect(self, agent_id: str) -> None:
        self.active_connections.pop(agent_id, None)
        self.subscriptions.pop(agent_id, None)

    def subscribe(self, agent_id: str, capabilities: list[str]) -> None:
        self.subscriptions[agent_id] = set(capabilities)

    async def broadcast_task(self, task: Task) -> None:
        """Broadcast a new task to relevant agents."""
        task_caps = set(task.specification.required_capabilities)
        message = Message(
            type=MessageType.TASK_PUBLISHED,
            payload={"task": json.loads(task.model_dump_json())},
        )
        for agent_id, websocket in self.active_connections.items():
            # Check if agent is subscribed to any of the task's capabilities
            agent_caps = self.subscriptions.get(agent_id, set())
            if not task_caps or not agent_caps or task_caps & agent_caps:
                try:
                    await websocket.send_json(message.to_dict())
                except Exception:
                    pass

    async def send_to_agent(self, agent_id: str, message: Message) -> None:
        """Send a message to a specific agent."""
        websocket = self.active_connections.get(agent_id)
        if websocket:
            try:
                await websocket.send_json(message.to_dict())
            except Exception:
                pass

    async def broadcast(self, message: Message) -> None:
        """Broadcast a message to all connected agents."""
        for websocket in self.active_connections.values():
            try:
                await websocket.send_json(message.to_dict())
            except Exception:
                pass


# -------------------------------------------------------------------------
# Global State
# -------------------------------------------------------------------------

task_board = TaskBoard()
auction_engine = AuctionEngine()
auction_scheduler = AuctionScheduler(auction_engine)
task_allocator = TaskAllocator(auction_engine)
reputation_ledger = ReputationLedger()
connection_manager = ConnectionManager()

# Background tasks
auction_runner_task: asyncio.Task | None = None


async def run_pending_auctions() -> None:
    """Background task to run auctions when they're due."""
    while True:
        try:
            due_task_ids = auction_scheduler.get_due_auctions()
            for task_id in due_task_ids:
                task = await task_board.get_task(task_id)
                if task and task.status == TaskStatus.OPEN:
                    bids = task_board.get_pending_bids(task_id)
                    scores = reputation_ledger.get_all_scores()

                    result, execution = await task_allocator.run_allocation(
                        task, bids, scores
                    )

                    # Update task and bids
                    if result.has_winner:
                        task = task_allocator.update_task_after_allocation(task, result)
                        await task_board.update_task_status(task_id, task.status)
                        task_allocator.update_bid_statuses(bids, result.winning_bid.bid_id)

                        if execution:
                            await task_board.create_execution(execution)

                            # Notify winner
                            await connection_manager.send_to_agent(
                                result.winner_id,
                                Message(
                                    type=MessageType.TASK_ASSIGNED,
                                    payload={
                                        "task_id": task_id,
                                        "execution_id": execution.execution_id,
                                        "price": result.final_price,
                                    },
                                ),
                            )

                    auction_scheduler.complete_auction(task_id)

        except Exception as e:
            print(f"Auction runner error: {e}")

        await asyncio.sleep(1)  # Check every second


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global auction_runner_task
    auction_runner_task = asyncio.create_task(run_pending_auctions())
    yield
    if auction_runner_task:
        auction_runner_task.cancel()


# -------------------------------------------------------------------------
# FastAPI App
# -------------------------------------------------------------------------

app = FastAPI(
    title="Agent Economy Market",
    description="Decentralized agent marketplace for task execution",
    version="0.1.0",
    lifespan=lifespan,
)


# -------------------------------------------------------------------------
# Agent Endpoints
# -------------------------------------------------------------------------


@app.post("/agents/register")
async def register_agent(request: RegisterAgentRequest) -> dict:
    """Register a new agent."""
    from economy.models import Capability, PricingModel, AutonomyLevel

    agent_id = str(ULID())
    profile = AgentProfile(
        agent_id=agent_id,
        name=request.name,
        description=request.description,
        capabilities=[Capability(name=c) for c in request.capabilities],
        pricing=PricingModel(base_rate=request.base_rate),
        autonomy_level=AutonomyLevel(request.autonomy_level),
    )
    await task_board.register_agent(profile)
    return {"agent_id": agent_id, "profile": json.loads(profile.model_dump_json())}


@app.get("/agents")
async def list_agents() -> list[dict]:
    """List all registered agents."""
    agents = task_board.get_all_agents()
    return [json.loads(a.model_dump_json()) for a in agents]


@app.get("/agents/online")
async def list_online_agents() -> list[dict]:
    """List all online agents."""
    agents = task_board.get_online_agents()
    return [json.loads(a.model_dump_json()) for a in agents]


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Get an agent by ID."""
    agent = task_board.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return json.loads(agent.model_dump_json())


@app.get("/agents/{agent_id}/reputation")
async def get_agent_reputation(agent_id: str) -> dict:
    """Get an agent's reputation summary."""
    summary = reputation_ledger.get_summary(agent_id)
    return json.loads(summary.model_dump_json())


@app.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str) -> dict:
    """Update agent's last seen timestamp."""
    await task_board.heartbeat(agent_id)
    return {"status": "ok"}


# -------------------------------------------------------------------------
# Task Endpoints
# -------------------------------------------------------------------------


@app.post("/tasks/publish")
async def publish_task(request: PublishTaskRequest) -> dict:
    """Publish a new task to the marketplace."""
    task_id = str(ULID())

    deadline = None
    if request.deadline_minutes:
        deadline = datetime.utcnow() + timedelta(minutes=request.deadline_minutes)

    task = Task(
        task_id=task_id,
        publisher_id="system",  # TODO: Get from auth
        specification=TaskSpec(
            title=request.title,
            description=request.description,
            required_capabilities=request.required_capabilities,
            inputs=request.inputs,
        ),
        budget=Budget(
            min_price=request.budget_min,
            max_price=request.budget_max,
        ),
        deadline=deadline,
        auction_duration=timedelta(minutes=request.auction_duration_minutes),
        allocation_method=AllocationMethod(request.allocation_method),
    )

    await task_board.publish_task(task)
    auction_scheduler.schedule_auction(task)

    # Broadcast to connected agents
    await connection_manager.broadcast_task(task)

    return {"task_id": task_id, "task": json.loads(task.model_dump_json())}


@app.get("/tasks")
async def list_tasks(
    status: str | None = None,
    limit: int = Query(default=50, le=100),
) -> list[dict]:
    """List tasks, optionally filtered by status."""
    if status:
        tasks = task_board.get_tasks_by_status(TaskStatus(status))
    else:
        tasks = task_board.get_all_tasks()
    return [json.loads(t.model_dump_json()) for t in tasks[:limit]]


@app.get("/tasks/open")
async def list_open_tasks() -> list[dict]:
    """List all open tasks."""
    tasks = task_board.get_open_tasks()
    return [json.loads(t.model_dump_json()) for t in tasks]


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get a task by ID."""
    task = await task_board.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(task.model_dump_json())


@app.get("/tasks/{task_id}/bids")
async def get_task_bids(task_id: str) -> list[dict]:
    """Get all bids for a task."""
    bids = task_board.get_bids(task_id)
    return [json.loads(b.model_dump_json()) for b in bids]


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    """Cancel a task."""
    await task_board.cancel_task(task_id)
    return {"status": "cancelled"}


# -------------------------------------------------------------------------
# Bid Endpoints
# -------------------------------------------------------------------------


@app.post("/bids/submit")
async def submit_bid(request: SubmitBidRequest) -> dict:
    """Submit a bid for a task."""
    bid_id = str(ULID())

    bid = Bid(
        bid_id=bid_id,
        task_id=request.task_id,
        agent_id=request.agent_id,
        price=request.price,
        estimated_duration=timedelta(minutes=request.estimated_minutes),
        confidence=request.confidence,
        proposed_approach=request.proposed_approach,
    )

    try:
        await task_board.submit_bid(bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"bid_id": bid_id, "bid": json.loads(bid.model_dump_json())}


@app.get("/bids/agent/{agent_id}")
async def get_agent_bids(agent_id: str) -> list[dict]:
    """Get all bids by an agent."""
    bids = task_board.get_agent_bids(agent_id)
    return [json.loads(b.model_dump_json()) for b in bids]


# -------------------------------------------------------------------------
# Execution Endpoints
# -------------------------------------------------------------------------


@app.get("/executions")
async def list_executions(limit: int = Query(default=50, le=100)) -> list[dict]:
    """List all executions."""
    executions = task_board.get_all_executions()
    return [json.loads(e.model_dump_json()) for e in executions[:limit]]


@app.get("/executions/{execution_id}")
async def get_execution(execution_id: str) -> dict:
    """Get an execution by ID."""
    execution = await task_board.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return json.loads(execution.model_dump_json())


@app.post("/executions/{execution_id}/start")
async def start_execution(execution_id: str) -> dict:
    """Mark execution as started."""
    execution = await task_board.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution.status = ExecutionStatus.IN_PROGRESS
    execution.started_at = datetime.utcnow()
    await task_board.update_execution(execution)

    # Update task status
    await task_board.update_task_status(execution.task_id, TaskStatus.IN_PROGRESS)

    return {"status": "started"}


@app.post("/executions/{execution_id}/complete")
async def complete_execution(
    execution_id: str, request: CompleteExecutionRequest
) -> dict:
    """Mark execution as complete."""
    execution = await task_board.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = datetime.utcnow()
    execution.result = ExecutionResult(
        output=request.output,
        output_type=request.output_type,
        execution_log=request.execution_log,
        actual_duration=execution.completed_at - execution.started_at
        if execution.started_at
        else timedelta(0),
    )
    await task_board.update_execution(execution)

    # Update task status
    await task_board.update_task_status(execution.task_id, TaskStatus.COMPLETED)

    # Record reputation
    task = await task_board.get_task(execution.task_id)
    if task:
        reputation_ledger.record_performance(
            execution.agent_id,
            task,
            execution,
            quality_score=0.8,  # TODO: Run evaluation
        )

    return {"status": "completed"}


@app.post("/executions/{execution_id}/fail")
async def fail_execution(execution_id: str, reason: str = "") -> dict:
    """Mark execution as failed."""
    execution = await task_board.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution.status = ExecutionStatus.FAILED
    execution.completed_at = datetime.utcnow()
    execution.failure_reason = reason
    await task_board.update_execution(execution)

    # Update task status
    await task_board.update_task_status(execution.task_id, TaskStatus.FAILED)

    # Record reputation (failed)
    task = await task_board.get_task(execution.task_id)
    if task:
        reputation_ledger.record_performance(
            execution.agent_id,
            task,
            execution,
            quality_score=0.0,
        )

    return {"status": "failed"}


# -------------------------------------------------------------------------
# Stats & Dashboard Endpoints
# -------------------------------------------------------------------------


@app.get("/stats")
async def get_market_stats() -> dict:
    """Get marketplace statistics."""
    board_stats = task_board.get_stats()
    reputation_stats = reputation_ledger.get_stats()

    return {
        "market": board_stats,
        "reputation": reputation_stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/reputation/leaderboard")
async def get_leaderboard(limit: int = Query(default=10, le=50)) -> list[dict]:
    """Get reputation leaderboard."""
    summaries = reputation_ledger.get_leaderboard(limit)
    return [json.loads(s.model_dump_json()) for s in summaries]


@app.get("/events")
async def get_events(limit: int = Query(default=100, le=500)) -> list[dict]:
    """Get recent events."""
    events = task_board.get_event_log()
    return events[-limit:]


# -------------------------------------------------------------------------
# WebSocket Endpoint
# -------------------------------------------------------------------------


@app.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket endpoint for real-time updates."""
    await connection_manager.connect(agent_id, websocket)
    try:
        # Update last seen
        await task_board.heartbeat(agent_id)

        while True:
            data = await websocket.receive_json()
            message = Message.from_dict(data)

            if message.type == MessageType.SUBSCRIBE:
                capabilities = message.payload.get("capabilities", [])
                connection_manager.subscribe(agent_id, capabilities)
                await websocket.send_json(
                    Message(
                        type=MessageType.RESPONSE,
                        payload={"subscribed": capabilities},
                    ).to_dict()
                )

            elif message.type == MessageType.AGENT_HEARTBEAT:
                await task_board.heartbeat(agent_id)

            elif message.type == MessageType.BID_SUBMITTED:
                bid_data = message.payload.get("bid", {})
                # Process bid...
                pass

    except WebSocketDisconnect:
        connection_manager.disconnect(agent_id)


# -------------------------------------------------------------------------
# Dashboard HTML
# -------------------------------------------------------------------------


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple HTML dashboard."""
    stats = await get_market_stats()
    agents = task_board.get_all_agents()
    tasks = task_board.get_all_tasks()
    executions = task_board.get_all_executions()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Agent Economy Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'JetBrains Mono', 'SF Mono', monospace; 
                background: #0d1117; 
                color: #c9d1d9; 
                padding: 2rem;
            }}
            h1 {{ color: #58a6ff; margin-bottom: 1.5rem; font-size: 1.5rem; }}
            h2 {{ color: #8b949e; margin: 1.5rem 0 1rem; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.1em; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
            .card {{ 
                background: #161b22; 
                border: 1px solid #30363d; 
                border-radius: 8px; 
                padding: 1.5rem;
            }}
            .card-value {{ font-size: 2rem; color: #58a6ff; font-weight: bold; }}
            .card-label {{ color: #8b949e; font-size: 0.85rem; margin-top: 0.5rem; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
            th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #30363d; }}
            th {{ color: #8b949e; font-weight: normal; font-size: 0.85rem; }}
            .status {{ padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; }}
            .status-open {{ background: #238636; }}
            .status-completed {{ background: #1f6feb; }}
            .status-failed {{ background: #da3633; }}
            .status-in_progress {{ background: #9e6a03; }}
            .online {{ color: #3fb950; }}
            .offline {{ color: #f85149; }}
        </style>
    </head>
    <body>
        <h1>🏛️ Agent Economy Dashboard</h1>
        
        <div class="grid">
            <div class="card">
                <div class="card-value">{stats['market']['agents']['total']}</div>
                <div class="card-label">Total Agents</div>
            </div>
            <div class="card">
                <div class="card-value">{stats['market']['agents']['online']}</div>
                <div class="card-label">Online Now</div>
            </div>
            <div class="card">
                <div class="card-value">{stats['market']['tasks']['total']}</div>
                <div class="card-label">Total Tasks</div>
            </div>
            <div class="card">
                <div class="card-value">{stats['market']['tasks']['open']}</div>
                <div class="card-label">Open Tasks</div>
            </div>
            <div class="card">
                <div class="card-value">{stats['market']['executions']['completed']}</div>
                <div class="card-label">Completed</div>
            </div>
            <div class="card">
                <div class="card-value">${stats['market']['economics']['total_transacted']:.2f}</div>
                <div class="card-label">Total Transacted</div>
            </div>
        </div>
        
        <h2>Agents</h2>
        <table>
            <tr>
                <th>Name</th>
                <th>ID</th>
                <th>Capabilities</th>
                <th>Status</th>
            </tr>
            {''.join(f'''
            <tr>
                <td>{a.name}</td>
                <td style="font-size:0.8rem; color:#8b949e">{a.agent_id[:8]}...</td>
                <td>{', '.join(a.capability_names) or '-'}</td>
                <td><span class="{'online' if (datetime.utcnow() - a.last_seen).seconds < 60 else 'offline'}">●</span></td>
            </tr>
            ''' for a in agents[:10])}
        </table>
        
        <h2>Recent Tasks</h2>
        <table>
            <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Budget</th>
                <th>Final Price</th>
            </tr>
            {''.join(f'''
            <tr>
                <td>{t.specification.title[:40]}</td>
                <td><span class="status status-{t.status.value}">{t.status.value}</span></td>
                <td>${t.budget.max_price:.2f}</td>
                <td>{f"${t.final_price:.2f}" if t.final_price else "-"}</td>
            </tr>
            ''' for t in tasks[:10])}
        </table>
        
        <h2>Recent Executions</h2>
        <table>
            <tr>
                <th>Execution ID</th>
                <th>Agent</th>
                <th>Status</th>
                <th>Price</th>
            </tr>
            {''.join(f'''
            <tr>
                <td style="font-size:0.8rem">{e.execution_id[:12]}...</td>
                <td style="font-size:0.8rem">{e.agent_id[:8]}...</td>
                <td><span class="status status-{e.status.value}">{e.status.value}</span></td>
                <td>${e.agreed_price:.2f}</td>
            </tr>
            ''' for e in executions[:10])}
        </table>
        
        <p style="margin-top: 2rem; color: #8b949e; font-size: 0.8rem;">
            Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} • Auto-refresh every 5s
        </p>
    </body>
    </html>
    """
    return html


# -------------------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------------------


def main():
    """Run the server."""
    import uvicorn

    uvicorn.run(
        "economy.network.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
