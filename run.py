#!/usr/bin/env python3
"""Quick start script for the agent economy."""

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path


def run_server():
    """Run the market server."""
    print("Starting market server on http://localhost:8000")
    print("Dashboard available at http://localhost:8000/dashboard")
    print("Press Ctrl+C to stop\n")

    import uvicorn
    uvicorn.run(
        "economy.network.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


def run_agent(agent_type: str, name: str, capabilities: str):
    """Run an agent."""
    caps = [c.strip() for c in capabilities.split(",")]

    async def main():
        if agent_type == "autonomous":
            from economy.agents.autonomous import AutonomousAgent
            agent = AutonomousAgent(name=name, capabilities=caps)
        elif agent_type == "simple":
            from economy.agents.base import SimpleAgent
            agent = SimpleAgent(name=name, capabilities=caps)
        elif agent_type == "human":
            from economy.agents.human_backed import HumanBackedAgent
            agent = HumanBackedAgent(name=name, capabilities=caps)
        elif agent_type == "manager":
            from economy.agents.manager import ManagerAgent
            agent = ManagerAgent(name=name)
        else:
            print(f"Unknown agent type: {agent_type}")
            return

        await agent.run()

    asyncio.run(main())


def run_demo():
    """Run a quick demo."""
    print("=" * 60)
    print("Agent Economy Demo")
    print("=" * 60)
    print("\nThis demo will:")
    print("  1. Start 3 simple agents")
    print("  2. Publish 5 sample tasks")
    print("  3. Watch agents bid and execute")
    print("\nMake sure the server is running first!")
    print("  python run.py server")
    print("\n" + "-" * 60)

    input("Press Enter to start...")

    async def main():
        from economy.agents.base import SimpleAgent
        from economy.network.client import MarketClient
        from examples.sample_tasks import SIMPLE_TASKS

        # Create agents
        print("\n[1/3] Creating agents...")
        agents = [
            SimpleAgent("CodeBot", ["coding", "review"]),
            SimpleAgent("WriteBot", ["writing", "summarization"]),
            SimpleAgent("AllBot", ["general", "coding", "writing"]),
        ]

        for agent in agents:
            await agent.start()
            print(f"  ✓ {agent.name} started")

        await asyncio.sleep(2)

        # Publish tasks
        print("\n[2/3] Publishing tasks...")
        client = MarketClient()
        await client.connect()

        for task_data in SIMPLE_TASKS[:5]:
            task = await client.publish_task(
                title=task_data["title"],
                description=task_data["description"],
                budget_max=task_data["budget_max"],
                required_capabilities=task_data.get("required_capabilities", []),
                auction_duration_minutes=1,
            )
            print(f"  ✓ Published: {task_data['title']}")

        # Wait for execution
        print("\n[3/3] Waiting for execution (60 seconds)...")
        for i in range(60, 0, -10):
            print(f"  {i} seconds remaining...")
            await asyncio.sleep(10)

        # Show results
        print("\n" + "=" * 60)
        print("Results")
        print("=" * 60)

        stats = await client.get_stats()
        market = stats.get("market", {})
        print(f"  Tasks completed: {market.get('tasks', {}).get('completed', 0)}")
        print(f"  Total transacted: ${market.get('economics', {}).get('total_transacted', 0):.2f}")

        # Cleanup
        for agent in agents:
            await agent.stop()
        await client.disconnect()

        print("\n✓ Demo complete!")

    asyncio.run(main())


def run_experiment(scenario: str):
    """Run an experiment scenario."""
    print(f"Running experiment: {scenario}")

    async def main():
        if scenario == "market_efficiency":
            from experiments.scenarios.market_efficiency import MarketEfficiencyExperiment
            results = await MarketEfficiencyExperiment.run_all()
            print(f"\nCompleted {len(results)} experiments")

        elif scenario == "specialization":
            from experiments.scenarios.specialization import SpecializationExperiment
            result = await SpecializationExperiment.run(duration_minutes=5)
            print(f"\nCompleted: {result.config.name}")

        elif scenario == "trust":
            from experiments.scenarios.trust_dynamics import TrustDynamicsExperiment
            results = await TrustDynamicsExperiment.run_all()
            print(f"\nCompleted {len(results)} experiments")

        else:
            print(f"Unknown scenario: {scenario}")
            print("Available: market_efficiency, specialization, trust")

    asyncio.run(main())


def main():
    parser = argparse.ArgumentParser(
        description="Agent Economy - Quick Start",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py server                    # Start the market server
  python run.py demo                      # Run a quick demo
  python run.py agent autonomous MyBot    # Run an autonomous agent
  python run.py experiment market         # Run market efficiency experiment

First time setup:
  pip install -e .
  python run.py server     # Terminal 1
  python run.py demo       # Terminal 2
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Server command
    subparsers.add_parser("server", help="Start the market server")

    # Demo command
    subparsers.add_parser("demo", help="Run a quick demo")

    # Agent command
    agent_parser = subparsers.add_parser("agent", help="Run an agent")
    agent_parser.add_argument(
        "type",
        choices=["autonomous", "simple", "human", "manager"],
        help="Agent type",
    )
    agent_parser.add_argument("name", nargs="?", default="MyAgent", help="Agent name")
    agent_parser.add_argument(
        "--capabilities", "-c",
        default="general,coding,writing",
        help="Comma-separated capabilities",
    )

    # Experiment command
    exp_parser = subparsers.add_parser("experiment", help="Run an experiment")
    exp_parser.add_argument(
        "scenario",
        choices=["market_efficiency", "specialization", "trust"],
        help="Experiment scenario",
    )

    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", help="Open the dashboard")
    dash_parser.add_argument("--cli", action="store_true", help="CLI dashboard")

    args = parser.parse_args()

    if args.command == "server":
        run_server()
    elif args.command == "demo":
        run_demo()
    elif args.command == "agent":
        run_agent(args.type, args.name, args.capabilities)
    elif args.command == "experiment":
        run_experiment(args.scenario)
    elif args.command == "dashboard":
        if args.cli:
            from economy.cli import dashboard
            dashboard()
        else:
            import webbrowser
            webbrowser.open("http://localhost:8000/dashboard")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
