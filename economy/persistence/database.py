"""SQLite database management."""

import aiosqlite
from pathlib import Path
from typing import Any


SCHEMA = """
-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    profile_json TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    publisher_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    allocation_method TEXT NOT NULL,
    budget_max REAL NOT NULL,
    task_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    assigned_at TEXT,
    completed_at TEXT,
    assigned_agent_id TEXT,
    final_price REAL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_publisher ON tasks(publisher_id);

-- Bids table
CREATE TABLE IF NOT EXISTS bids (
    bid_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    bid_json TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

CREATE INDEX IF NOT EXISTS idx_bids_task ON bids(task_id);
CREATE INDEX IF NOT EXISTS idx_bids_agent ON bids(agent_id);

-- Executions table
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    bid_id TEXT NOT NULL,
    agreed_price REAL NOT NULL,
    status TEXT NOT NULL,
    execution_json TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (bid_id) REFERENCES bids(bid_id)
);

CREATE INDEX IF NOT EXISTS idx_executions_task ON executions(task_id);
CREATE INDEX IF NOT EXISTS idx_executions_agent ON executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);

-- Performance records (for reputation)
CREATE TABLE IF NOT EXISTS performance_records (
    record_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    completed INTEGER NOT NULL,
    on_time INTEGER NOT NULL,
    quality_score REAL NOT NULL,
    bid_price REAL NOT NULL,
    final_price REAL NOT NULL,
    record_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
);

CREATE INDEX IF NOT EXISTS idx_perf_agent ON performance_records(agent_id);
CREATE INDEX IF NOT EXISTS idx_perf_timestamp ON performance_records(timestamp);

-- Reputation summaries (cached)
CREATE TABLE IF NOT EXISTS reputation_summaries (
    agent_id TEXT PRIMARY KEY,
    overall_score REAL NOT NULL,
    completion_rate REAL NOT NULL,
    on_time_rate REAL NOT NULL,
    average_quality REAL NOT NULL,
    total_tasks INTEGER NOT NULL,
    total_earnings REAL NOT NULL,
    summary_json TEXT NOT NULL,
    computed_at TEXT NOT NULL
);

-- Events log
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
"""


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str | Path = "economy.db") -> None:
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to the database."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

    async def disconnect(self) -> None:
        """Disconnect from the database."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        return self._connection

    async def execute(
        self, query: str, params: tuple = ()
    ) -> aiosqlite.Cursor:
        """Execute a query."""
        return await self.connection.execute(query, params)

    async def executemany(
        self, query: str, params_list: list[tuple]
    ) -> aiosqlite.Cursor:
        """Execute a query with multiple parameter sets."""
        return await self.connection.executemany(query, params_list)

    async def fetchone(
        self, query: str, params: tuple = ()
    ) -> dict[str, Any] | None:
        """Fetch a single row."""
        cursor = await self.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchall(
        self, query: str, params: tuple = ()
    ) -> list[dict[str, Any]]:
        """Fetch all rows."""
        cursor = await self.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.connection.commit()

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
