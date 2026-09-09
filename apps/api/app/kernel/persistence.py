"""Durable Agent task snapshots with a provider-neutral storage contract."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.kernel.interfaces.loop import (
    AgentTask,
    Budget,
    Observation,
    Step,
    StepStatus,
    TaskStatus,
    ToolCall,
    Turn,
    TurnSettings,
)


class ITaskStore(ABC):
    """Persistence contract for task snapshots and resume."""

    @abstractmethod
    def save(self, task: AgentTask) -> None:
        """Create or replace a complete task snapshot."""
        ...

    @abstractmethod
    def get(self, task_id: str) -> AgentTask | None:
        """Load a task snapshot by id."""
        ...

    @abstractmethod
    def delete(self, task_id: str) -> None:
        """Delete a persisted task."""
        ...

    @abstractmethod
    def list_ids(self) -> list[str]:
        """List persisted task ids, newest first."""
        ...


class SQLiteTaskStore(ITaskStore):
    """Small SQLite-backed store suitable for local development and tests."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task_snapshots (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, task: AgentTask) -> None:
        now = datetime.utcnow().isoformat()
        payload = json.dumps(_task_to_dict(task), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_task_snapshots(task_id, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET updated_at=excluded.updated_at,
                                                   payload=excluded.payload
                """,
                (task.id, task.created_at.isoformat(), now, payload),
            )

    def get(self, task_id: str) -> AgentTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM agent_task_snapshots WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _task_from_dict(json.loads(row[0])) if row else None

    def delete(self, task_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM agent_task_snapshots WHERE task_id = ?", (task_id,)
            )

    def list_ids(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM agent_task_snapshots ORDER BY updated_at DESC"
            ).fetchall()
        return [row[0] for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


def _task_to_dict(task: AgentTask) -> dict[str, Any]:
    """Serialize the dataclass graph without relying on pickle."""
    return _json_safe(asdict(task))


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _task_from_dict(data: dict[str, Any]) -> AgentTask:
    """Rehydrate a task snapshot with explicit version-tolerant defaults."""
    turns: list[Turn] = []
    for turn_data in data.get("turns", []):
        settings_data = turn_data["settings_snapshot"]
        budget_data = settings_data.get("budget", {})
        settings = TurnSettings(
            model=settings_data.get("model", "unknown"),
            system_prompt=settings_data.get("system_prompt", ""),
            budget=Budget(**budget_data),
            tool_names=frozenset(settings_data.get("tool_names", [])),
            extra=settings_data.get("extra", {}),
        )
        steps: list[Step] = []
        for step_data in turn_data.get("steps", []):
            calls = [ToolCall(**call) for call in step_data.get("tool_calls", [])]
            observations = [Observation(**obs) for obs in step_data.get("observations", [])]
            steps.append(
                Step(
                    id=step_data["id"],
                    turn_id=step_data["turn_id"],
                    model_request=step_data.get("model_request", {}),
                    model_response=step_data.get("model_response", {}),
                    tool_calls=calls,
                    observations=observations,
                    status=StepStatus(step_data.get("status", StepStatus.PENDING.value)),
                    started_at=_datetime(step_data.get("started_at")),
                    finished_at=_datetime(step_data.get("finished_at")),
                    tokens_used=step_data.get("tokens_used", 0),
                )
            )
        turns.append(
            Turn(
                id=turn_data["id"],
                task_id=turn_data["task_id"],
                settings_snapshot=settings,
                user_input=turn_data.get("user_input"),
                steps=steps,
                started_at=_datetime(turn_data.get("started_at")) or datetime.utcnow(),
                finished_at=_datetime(turn_data.get("finished_at")),
            )
        )
    return AgentTask(
        id=data["id"],
        goal=data["goal"],
        context=data.get("context", {}),
        turns=turns,
        status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
        created_at=_datetime(data.get("created_at")) or datetime.utcnow(),
        completed_at=_datetime(data.get("completed_at")),
    )


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
