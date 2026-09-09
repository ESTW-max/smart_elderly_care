"""Context assembly and budget management for long-running Agent tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudget:
    """Independent budgets for message text, tool output, and total context."""

    max_total_tokens: int = 16_000
    max_message_tokens: int = 8_000
    max_tool_output_tokens: int = 6_000


class ContextManager:
    """
    Assemble model history under explicit budgets.

    The initial implementation uses a deterministic character-to-token
    estimate (four characters per token). It preserves system/current user
    messages and keeps the newest history first, preventing old tool output
    from consuming the entire model window. The policy is intentionally
    isolated so a model-specific tokenizer or summarizer can replace it.
    """

    def __init__(self, budget: ContextBudget | None = None) -> None:
        self._budget = budget or ContextBudget()

    @property
    def budget(self) -> ContextBudget:
        """Return the immutable context budget."""
        return self._budget

    def build(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        """
        Return budgeted messages and whether history was compacted.

        System and the first user message are retained. Older messages are
        discarded before newer messages. Assistant tool calls and their
        results are kept or discarded together. Tool output is truncated
        at head/tail boundaries within its separate budget.
        """
        if not messages:
            return [], False

        normalized: list[dict[str, Any]] = []
        compacted = False
        for message in messages:
            item = dict(message)
            if isinstance(item.get("content"), str):
                item["content"], was_truncated = self._truncate_tokens(
                    item["content"], self._budget.max_message_tokens
                )
                compacted = compacted or was_truncated
            normalized.append(item)

        preserved: list[dict[str, Any]] = [normalized[0]]
        if len(messages) > 1 and messages[1].get("role") == "user":
            preserved.append(normalized[1])

        history = normalized[len(preserved) :]
        units, had_orphans = self._interaction_units(history)
        budgeted_history: list[dict[str, Any]] = []
        tool_tokens = 0
        total_tokens = sum(self._estimate_tokens(message) for message in preserved)
        compacted = compacted or had_orphans

        for unit in reversed(units):
            candidate: list[dict[str, Any]] = []
            candidate_tool_tokens = tool_tokens
            unit_compacted = False
            for message in unit:
                item = dict(message)
                if item.get("role") == "tool":
                    content = str(item.get("content") or "")
                    remaining = self._budget.max_tool_output_tokens - candidate_tool_tokens
                    if remaining <= 0:
                        break
                    item["content"], was_truncated = self._truncate_tokens(content, remaining)
                    unit_compacted = unit_compacted or was_truncated
                    candidate_tool_tokens += self._estimate_tokens(item)
                candidate.append(item)

            if len(candidate) != len(unit):
                compacted = True
                continue

            unit_tokens = sum(self._estimate_tokens(item) for item in candidate)
            if total_tokens + unit_tokens > self._budget.max_total_tokens:
                compacted = True
                continue
            budgeted_history[0:0] = candidate
            total_tokens += unit_tokens
            tool_tokens = candidate_tool_tokens
            compacted = compacted or unit_compacted

        return preserved + budgeted_history, compacted

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        """Estimate tokens conservatively until a model tokenizer is injected."""
        content = str(message.get("content") or "")
        return max(1, (len(content) + 3) // 4)

    @staticmethod
    def _interaction_units(
        history: list[dict[str, Any]],
    ) -> tuple[list[list[dict[str, Any]]], bool]:
        """Group assistant tool calls with their following tool results.

        Tool results without a matching assistant call are discarded rather
        than emitted as orphan messages, since providers reject that shape.
        """
        units: list[list[dict[str, Any]]] = []
        had_orphans = False
        index = 0
        while index < len(history):
            message = history[index]
            if message.get("role") == "tool":
                units.append([message])
                had_orphans = True
                index += 1
                continue
            if message.get("role") == "assistant" and message.get("tool_calls"):
                call_ids = {
                    str(call.get("id"))
                    for call in message.get("tool_calls") or []
                    if isinstance(call, dict) and call.get("id") is not None
                }
                pending_ids = set(call_ids)
                unit = [message]
                index += 1
                while index < len(history) and history[index].get("role") == "tool":
                    result = history[index]
                    result_id = str(result.get("tool_call_id"))
                    if result_id in pending_ids:
                        unit.append(result)
                        pending_ids.remove(result_id)
                    else:
                        had_orphans = True
                    index += 1
                if pending_ids or not call_ids:
                    had_orphans = True
                    continue
                units.append(unit)
                continue
            units.append([message])
            index += 1
        return units, had_orphans

    @staticmethod
    def _truncate_tokens(content: str, max_tokens: int) -> tuple[str, bool]:
        if max_tokens <= 0:
            return "", bool(content)
        max_chars = max_tokens * 4
        if len(content) <= max_chars:
            return content, False
        marker = "\n[… context truncated …]\n"
        if max_chars < len(marker):
            marker = "…"
        available = max_chars - len(marker)
        head = available // 2
        tail = available - head
        return content[:head] + marker + (content[-tail:] if tail else ""), True
