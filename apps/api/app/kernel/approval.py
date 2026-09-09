"""Persistent, exact-action approval workflow for high-risk Agent tools."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.kernel.interfaces.tool import ITool, IToolApproval


class ApprovalStatus(str, Enum):
    """Lifecycle state of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class ApprovalRequest:
    """Public approval record without credentials or execution internals."""

    id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None
    task_id: str | None = None


class SQLiteApprovalStore(IToolApproval):
    """Fail-closed approval service backed by SQLite.

    An approval applies exactly once to a task, canonical tool name, and
    arguments. Unknown actions create a pending request and return false.
    Approved actions are atomically consumed before execution to prevent replay.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    action_hash TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )
            self._ensure_task_id_column(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_approvals_action "
                "ON agent_approvals(task_id, action_hash, status)"
            )

    async def approve(
        self,
        tool: ITool,
        arguments: dict[str, Any],
        task_id: str | None = None,
    ) -> bool:
        action_hash = _action_hash(tool.schema.qualified_name, arguments)
        with self._connect() as connection:
            approved = connection.execute(
                "SELECT id FROM agent_approvals "
                "WHERE action_hash = ? AND status = ? AND task_id IS ? "
                "ORDER BY created_at LIMIT 1",
                (action_hash, ApprovalStatus.APPROVED.value, task_id),
            ).fetchone()
            if approved:
                connection.execute(
                    "UPDATE agent_approvals SET status = ? WHERE id = ?",
                    (ApprovalStatus.CONSUMED.value, approved[0]),
                )
                return True
            existing = connection.execute(
                "SELECT id FROM agent_approvals "
                "WHERE action_hash = ? AND status = ? AND task_id IS ? LIMIT 1",
                (action_hash, ApprovalStatus.PENDING.value, task_id),
            ).fetchone()
            if not existing:
                connection.execute(
                    """
                    INSERT INTO agent_approvals(
                        id, task_id, action_hash, tool_name, arguments, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        task_id,
                        action_hash,
                        tool.schema.qualified_name,
                        json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                        ApprovalStatus.PENDING.value,
                        datetime.now(UTC).isoformat(),
                    ),
                )
        return False

    def list(
        self,
        status: ApprovalStatus | None = None,
        task_id: str | None = None,
    ) -> list[ApprovalRequest]:
        query = (
            "SELECT id, tool_name, arguments, status, created_at, decided_at, task_id "
            "FROM agent_approvals"
        )
        clauses: list[str] = []
        parameters: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if task_id is not None:
            clauses.append("task_id = ?")
            parameters.append(task_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [_record(row) for row in rows]

    def decide(self, approval_id: str, approved: bool) -> ApprovalRequest | None:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        decided_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE agent_approvals SET status = ?, decided_at = ? "
                "WHERE id = ? AND status = ?",
                (status.value, decided_at, approval_id, ApprovalStatus.PENDING.value),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT id, tool_name, arguments, status, created_at, decided_at, task_id "
                "FROM agent_approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        return _record(row)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _ensure_task_id_column(connection: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_approvals)").fetchall()
        }
        if "task_id" not in columns:
            connection.execute("ALTER TABLE agent_approvals ADD COLUMN task_id TEXT")


def _action_hash(tool_name: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _record(row: tuple[str, str, str, str, str, str | None, str | None]) -> ApprovalRequest:
    return ApprovalRequest(
        id=row[0],
        tool_name=row[1],
        arguments=json.loads(row[2]),
        status=ApprovalStatus(row[3]),
        created_at=datetime.fromisoformat(row[4]),
        decided_at=datetime.fromisoformat(row[5]) if row[5] else None,
        task_id=row[6],
    )
