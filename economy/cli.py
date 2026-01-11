"""Command-line interface for the agent economy."""

import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

app = typer.Typer(
    name="agent-economy",
    help="Autonomous agent economy for task execution and coordination",
)
console = Console()

# Sub-commands
server_app = typer.Typer(help="Server management")
agent_app = typer.Typer(help="Agent management")
task_app = typer.Typer(help="Task management")

app.add_typer(server_app, name="server")
app.add_typer(agent_app, name="agent")
app.add_typer(task_app, name="task")


# -------------------------------------------------------------------------
# Server Commands
# -------------------------------------------------------------------------


@server_app.command("start")
def start_server(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the market server."""
    import uvicorn

    console.print(f"[bold green]Starting market server on {host}:{port}[/bold green]")
    uvicorn.run(
        "economy.network.server:app",
        host=host,
        port=port,
        reload=reload,
    )


# -------------------------------------------------------------------------
# Agent Commands
# -------------------------------------------------------------------------


@agent_app.command("run")
def run_agent(
    agent_type: str = typer.Option("autonomous", help="Agent type: autonomous, human, manager"),
    name: str = typer.Option("Agent", help="Agent name"),
    capabilities: str = typer.Option("general", help="Comma-separated capabilities"),
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
    model: str = typer.Option("gpt-4o-mini", help="LLM model for autonomous agents"),
):
    """Run an agent."""
    cap_list = [c.strip() for c in capabilities.split(",")]

    async def main():
        if agent_type == "autonomous":
            from economy.agents.autonomous import AutonomousAgent
            agent = AutonomousAgent(
                name=name,
                capabilities=cap_list,
                server_url=server,
                model=model,
            )
        elif agent_type == "human":
            from economy.agents.human_backed import HumanBackedAgent
            agent = HumanBackedAgent(
                name=name,
                capabilities=cap_list,
                server_url=server,
            )
        elif agent_type == "manager":
            from economy.agents.manager import ManagerAgent
            agent = ManagerAgent(
                name=name,
                server_url=server,
                model=model,
            )
        else:
            console.print(f"[red]Unknown agent type: {agent_type}[/red]")
            return

        await agent.run()

    asyncio.run(main())


@agent_app.command("list")
def list_agents(
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
):
    """List all registered agents."""
    import httpx

    try:
        response = httpx.get(f"{server}/agents")
        agents = response.json()

        table = Table(title="Registered Agents")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Capabilities")
        table.add_column("Autonomy")
        table.add_column("Status")

        for agent in agents:
            agent_id = agent["agent_id"][:12] + "..."
            caps = ", ".join(c["name"] for c in agent.get("capabilities", []))
            status = "🟢" if agent.get("availability", {}).get("available_now") else "🔴"
            table.add_row(
                agent_id,
                agent["name"],
                caps or "-",
                agent.get("autonomy_level", "unknown"),
                status,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# -------------------------------------------------------------------------
# Task Commands
# -------------------------------------------------------------------------


@task_app.command("publish")
def publish_task(
    title: str = typer.Option(..., help="Task title"),
    description: str = typer.Option("", help="Task description"),
    budget: float = typer.Option(10.0, help="Maximum budget"),
    capabilities: str = typer.Option("", help="Required capabilities (comma-separated)"),
    auction_minutes: int = typer.Option(5, help="Auction duration in minutes"),
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
):
    """Publish a new task."""
    import httpx

    cap_list = [c.strip() for c in capabilities.split(",") if c.strip()]

    try:
        response = httpx.post(
            f"{server}/tasks/publish",
            json={
                "title": title,
                "description": description or title,
                "budget_max": budget,
                "required_capabilities": cap_list,
                "auction_duration_minutes": auction_minutes,
            },
        )
        response.raise_for_status()
        data = response.json()

        console.print(Panel(
            f"""[bold green]Task Published![/bold green]

Task ID: {data['task_id']}
Title: {title}
Budget: ${budget:.2f}
Auction ends in: {auction_minutes} minutes""",
            title="✅ Success",
        ))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@task_app.command("list")
def list_tasks(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
):
    """List tasks."""
    import httpx

    try:
        params = {}
        if status:
            params["status"] = status

        response = httpx.get(f"{server}/tasks", params=params)
        tasks = response.json()

        table = Table(title="Tasks")
        table.add_column("ID", style="dim")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Budget")
        table.add_column("Final Price")

        for task in tasks[:20]:
            task_id = task["task_id"][:12] + "..."
            status_emoji = {
                "open": "🟢",
                "assigned": "🟡",
                "in_progress": "🔵",
                "completed": "✅",
                "failed": "❌",
            }.get(task["status"], "⚪")

            table.add_row(
                task_id,
                task["specification"]["title"][:40],
                f"{status_emoji} {task['status']}",
                f"${task['budget']['max_price']:.2f}",
                f"${task['final_price']:.2f}" if task.get("final_price") else "-",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# -------------------------------------------------------------------------
# Dashboard Command
# -------------------------------------------------------------------------


@app.command("dashboard")
def dashboard(
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
    web: bool = typer.Option(False, help="Open web dashboard instead"),
    refresh: int = typer.Option(5, help="Refresh interval in seconds"),
):
    """Show economy dashboard."""
    if web:
        import webbrowser
        url = f"{server}/dashboard"
        console.print(f"[cyan]Opening {url} in browser...[/cyan]")
        webbrowser.open(url)
        return

    import httpx

    def get_stats():
        try:
            response = httpx.get(f"{server}/stats", timeout=5)
            return response.json()
        except Exception:
            return None

    def get_agents():
        try:
            response = httpx.get(f"{server}/agents", timeout=5)
            return response.json()
        except Exception:
            return []

    def get_tasks():
        try:
            response = httpx.get(f"{server}/tasks", timeout=5)
            return response.json()
        except Exception:
            return []

    def make_layout():
        stats = get_stats()
        agents = get_agents()
        tasks = get_tasks()

        if not stats:
            return Panel("[red]Cannot connect to server[/red]", title="Error")

        # Stats panel
        market = stats.get("market", {})
        econ = market.get("economics", {})

        stats_text = f"""
[bold cyan]Agents[/bold cyan]
  Total: {market.get('agents', {}).get('total', 0)}
  Online: {market.get('agents', {}).get('online', 0)}

[bold cyan]Tasks[/bold cyan]
  Total: {market.get('tasks', {}).get('total', 0)}
  Open: {market.get('tasks', {}).get('open', 0)}
  Completed: {market.get('tasks', {}).get('completed', 0)}
  Failed: {market.get('tasks', {}).get('failed', 0)}

[bold cyan]Economics[/bold cyan]
  Total Transacted: ${econ.get('total_transacted', 0):.2f}
  Avg Price: ${econ.get('average_price', 0):.2f}
"""

        # Agents table
        agent_table = Table(title="Agents", box=None)
        agent_table.add_column("Name")
        agent_table.add_column("Type")
        agent_table.add_column("●")
        for a in agents[:5]:
            agent_table.add_row(
                a["name"][:15],
                a.get("autonomy_level", "?")[:8],
                "[green]●[/green]" if a.get("availability", {}).get("available_now") else "[red]●[/red]",
            )

        # Tasks table
        task_table = Table(title="Recent Tasks", box=None)
        task_table.add_column("Title")
        task_table.add_column("Status")
        for t in tasks[:5]:
            task_table.add_row(
                t["specification"]["title"][:20],
                t["status"],
            )

        layout = Layout()
        layout.split_row(
            Layout(Panel(stats_text, title="📊 Statistics"), name="stats"),
            Layout(name="right"),
        )
        layout["right"].split_column(
            Layout(Panel(agent_table, title="🤖 Agents"), name="agents"),
            Layout(Panel(task_table, title="📋 Tasks"), name="tasks"),
        )

        return layout

    console.print("[bold]Agent Economy Dashboard[/bold]")
    console.print(f"Server: {server}")
    console.print(f"Refreshing every {refresh}s. Press Ctrl+C to exit.\n")

    try:
        with Live(make_layout(), refresh_per_second=1, console=console) as live:
            while True:
                live.update(make_layout())
                import time
                time.sleep(refresh)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard closed[/yellow]")


# -------------------------------------------------------------------------
# Stats Command
# -------------------------------------------------------------------------


@app.command("stats")
def show_stats(
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show economy statistics."""
    import httpx

    try:
        response = httpx.get(f"{server}/stats")
        stats = response.json()

        if json_output:
            console.print(json.dumps(stats, indent=2))
            return

        market = stats.get("market", {})
        reputation = stats.get("reputation", {})

        console.print(Panel(f"""
[bold cyan]Market Statistics[/bold cyan]

Agents:
  • Total registered: {market.get('agents', {}).get('total', 0)}
  • Currently online: {market.get('agents', {}).get('online', 0)}

Tasks:
  • Total: {market.get('tasks', {}).get('total', 0)}
  • Open: {market.get('tasks', {}).get('open', 0)}
  • Completed: {market.get('tasks', {}).get('completed', 0)}
  • Failed: {market.get('tasks', {}).get('failed', 0)}

Executions:
  • Total: {market.get('executions', {}).get('total', 0)}
  • Completed: {market.get('executions', {}).get('completed', 0)}
  • In Progress: {market.get('executions', {}).get('in_progress', 0)}

Economics:
  • Total transacted: ${market.get('economics', {}).get('total_transacted', 0):.2f}
  • Average price: ${market.get('economics', {}).get('average_price', 0):.2f}

Reputation:
  • Agents tracked: {reputation.get('agents_tracked', 0)}
  • Average score: {reputation.get('average_score', 0):.2f}
  • Completion rate: {reputation.get('completion_rate', 0):.1%}
""", title="📊 Economy Statistics"))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# -------------------------------------------------------------------------
# Demo Command
# -------------------------------------------------------------------------


@app.command("demo")
def run_demo(
    server: str = typer.Option("http://localhost:8000", help="Server URL"),
):
    """Run a demonstration of the economy."""
    console.print(Panel("""
[bold]Agent Economy Demo[/bold]

This will:
1. Register a few sample agents
2. Publish some tasks
3. Show the agents bidding and executing

Make sure the server is running first with:
  [cyan]agent-economy server start[/cyan]
""", title="🎭 Demo"))

    if not typer.confirm("Start the demo?"):
        return

    async def main():
        from economy.agents.autonomous import AutonomousAgent
        from economy.agents.base import SimpleAgent
        from economy.network.client import MarketClient

        # Create agents
        console.print("\n[bold]Creating agents...[/bold]")

        agents = [
            SimpleAgent(
                name="CodeBot",
                capabilities=["coding", "review"],
                server_url=server,
            ),
            SimpleAgent(
                name="ResearchBot",
                capabilities=["research", "summarization"],
                server_url=server,
            ),
            SimpleAgent(
                name="WriterBot",
                capabilities=["writing", "editing"],
                server_url=server,
            ),
        ]

        # Start agents
        for agent in agents:
            await agent.start()
            console.print(f"  ✅ {agent.name} started")

        # Give agents time to register
        await asyncio.sleep(2)

        # Publish some tasks
        console.print("\n[bold]Publishing tasks...[/bold]")

        client = MarketClient(server_url=server)
        await client.connect()

        tasks_to_publish = [
            {
                "title": "Review this Python function",
                "description": "Please review this code for bugs and improvements: def add(a, b): return a + b",
                "budget_max": 5.0,
                "required_capabilities": ["coding", "review"],
            },
            {
                "title": "Summarize recent AI news",
                "description": "Provide a brief summary of the latest developments in AI",
                "budget_max": 3.0,
                "required_capabilities": ["research", "summarization"],
            },
            {
                "title": "Write a haiku about programming",
                "description": "Compose a haiku (5-7-5 syllable poem) about the joys of programming",
                "budget_max": 2.0,
                "required_capabilities": ["writing"],
            },
        ]

        for task_data in tasks_to_publish:
            task = await client.publish_task(**task_data, auction_duration_minutes=1)
            console.print(f"  📋 Published: {task_data['title']}")

        console.print("\n[cyan]Waiting for auctions to complete (60 seconds)...[/cyan]")
        console.print("[dim]Watch the agent logs above for bidding activity[/dim]")

        # Wait for auctions
        await asyncio.sleep(65)

        # Show results
        console.print("\n[bold]Results:[/bold]")
        stats = await client.get_stats()
        console.print(f"  Completed: {stats['market']['executions']['completed']}")
        console.print(f"  Total transacted: ${stats['market']['economics']['total_transacted']:.2f}")

        # Clean up
        for agent in agents:
            await agent.stop()

        await client.disconnect()
        console.print("\n[green]Demo complete![/green]")

    asyncio.run(main())


# -------------------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------------------


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
