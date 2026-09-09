"""Minimal append-only audit event store for Agent security decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SQLiteAuditStore:
    """Persist security events without storing secrets or raw credentials."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    tool_name TEXT,
                    decision TEXT,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        event_type: str,
        *,
        task_id: str | None = None,
        tool_name: str | None = None,
        decision: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        safe_details = _redact(details or {})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_audit_events(
                    event_type, task_id, tool_name, decision, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    task_id,
                    tool_name,
                    decision,
                    json.dumps(safe_details, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_type, task_id, tool_name, decision, details, created_at "
                "FROM agent_audit_events ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [
            {
                "event_type": row[0],
                "task_id": row[1],
                "tool_name": row[2],
                "decision": row[3],
                "details": json.loads(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


def _redact(value: Any) -> Any:
    """Recursively redact likely credentials from audit details."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(
                secret in key.lower()
                for secret in ("key", "token", "secret", "password", "credential")
            )
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
