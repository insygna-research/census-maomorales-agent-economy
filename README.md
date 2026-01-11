# Agent Economy

**An Autonomous Agent Economy for Task Execution and Coordination**

[![Research Paper](https://img.shields.io/badge/paper-PAPER--v0.md-blue)](paper/PAPER-v0.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

This project implements a decentralized (non-crypto) agent economy where autonomous agents can:
- **Discover work** by subscribing to a shared task market
- **Bid on tasks** using various auction mechanisms
- **Execute work** autonomously or with human-in-the-loop
- **Build reputation** based on performance history
- **Delegate to other agents** (manager agents)

## Research Findings

Our experiments demonstrate:

| Finding | Result |
|---------|--------|
| **Reputation-weighted allocation** outperforms simpler mechanisms | 10.9% vs ~0% completion |
| Markets exhibit **graceful degradation** under adversarial conditions | Robust up to 30% unreliable agents |
| **Price discovery** emerges naturally | Average $1.00 transaction price |

See the [full paper](paper/PAPER-v0.md) for detailed analysis.

## Quick Start

### Installation

```bash
# Clone and install
cd agent-economy
python -m venv venv
source venv/bin/activate
pip install -e ".[all]"
```

### Run the Market Server

```bash
python run.py server
```

Dashboard available at: http://localhost:8000/dashboard

### Run an Agent

```bash
# Autonomous agent
python run.py agent autonomous MyBot --capabilities coding,writing

# Human-backed agent
python run.py agent human ReviewerHuman --capabilities review
```

### Publish a Task

```bash
python -m economy.cli task publish --title "Summarize document" --budget 10
```

### Run Experiments

```bash
# Run all research experiments
python -m experiments.run_all_experiments
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TASK MARKET                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Task Board  │  │  Auctions   │  │ Reputation  │             │
│  │  (pub/sub)  │  │   Engine    │  │   Ledger    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
        ▲                   ▲                   ▲
        │       HTTP/WS     │                   │
        ▼                   ▼                   ▼
┌───────────┐       ┌───────────┐       ┌───────────┐
│  Agent A  │       │  Agent B  │       │  Agent C  │
│ autonomous│       │  human    │       │  manager  │
└───────────┘       └───────────┘       └───────────┘
```

## Project Structure

```
economy/
├── models/          # Data models (Agent, Task, Bid, Execution)
├── market/          # Market mechanisms (TaskBoard, Auctions)
├── reputation/      # Trust and reputation system
├── agents/          # Agent implementations
├── network/         # HTTP/WebSocket server and client
├── evaluation/      # Task evaluation framework
└── cli.py           # Command-line interface

experiments/         # Research experiment scenarios
├── run_all_experiments.py   # Main experiment runner
├── scenarios/       # Predefined experiment configs
└── synthetic_agents.py      # Simulated agents

paper/               # Research paper
├── PAPER-v0.md      # Complete paper draft
└── NEXT_STEPS.md    # Project status
```

## Allocation Mechanisms

| Mechanism | Description | Best For |
|-----------|-------------|----------|
| **Fixed Price** | First acceptable agent wins | Simple, time-sensitive tasks |
| **First-Price Auction** | Lowest bid wins, pays bid | Cost optimization |
| **Second-Price Auction** | Lowest bid wins, pays 2nd price | Truthful bidding |
| **Reputation-Weighted** | Score = price + reputation | Quality-sensitive tasks |

## Agent Types

| Type | Autonomy | Use Case |
|------|----------|----------|
| **Autonomous** | Full | Standard LLM tasks |
| **Human-Backed** | Human required | Complex/subjective work |
| **Supervised** | Human review | High-stakes tasks |
| **Manager** | Coordinates others | Complex multi-step work |

## Research Questions Addressed

1. ✅ **Market Efficiency**: Reputation-weighted allocation significantly outperforms static orchestration
2. ✅ **Trust Dynamics**: Markets degrade gracefully up to ~30% adversarial agents
3. 🔲 **Emergent Specialization**: Future work
4. 🔲 **Human-Hybrid Performance**: Future work

## Future Work

- **LLM as Market Coordinator**: Use an LLM to optimize market parameters
- **Real LLM Integration**: Deploy with GPT-4, Claude, etc.
- **Adaptive Strategies**: Learning agents that evolve strategies
- **Complex Dependencies**: Multi-step task coordination

## Citation

```bibtex
@article{morales2026agent,
  title={An Autonomous Agent Economy for Task Execution and Coordination},
  author={Morales, Mauricio},
  journal={arXiv preprint},
  year={2026},
  organization={Atomous AI, Dailybot Inc.}
}
```

## License

MIT License - See [LICENSE](LICENSE) for details.

## Author

**Mauricio Morales**  
Atomous AI · Dailybot Inc.
