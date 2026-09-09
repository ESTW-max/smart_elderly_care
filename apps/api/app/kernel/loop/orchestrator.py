"""
Orchestrator - The main agent loop: sample → decide → act → observe.

Single Responsibility: Orchestrator drives the loop hierarchy
(Task → Turn → Step) and delegates execution details to StepRunner.

Dependency Inversion: it depends on IToolExecutor, IToolRegistry, and
ITerminationCondition abstractions — no concrete tool or environment here.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from app.kernel.context import ContextManager
from app.kernel.interfaces.loop import (
    AgentTask,
    Budget,
    IOrchestrator,
    SteeringMessage,
    Step,
    TaskStatus,
    Turn,
    TurnSettings,
)
from app.kernel.interfaces.tool import IToolExecutor, IToolRegistry
from app.kernel.loop.step import StepRunner
from app.kernel.loop.termination import TerminationChain
from app.kernel.model.interfaces import IModelProvider
from app.kernel.persistence import ITaskStore


class Orchestrator(IOrchestrator):
    """
    Concrete orchestration loop.

    Constructor arguments are the only injection points so the
    orchestrator is fully testable by passing mock implementations.

    Usage::

        orchestrator = Orchestrator(
            executor=my_executor,
            registry=my_registry,
        )
        task = await orchestrator.run(task)
    """

    def __init__(
        self,
        executor: IToolExecutor,
        registry: IToolRegistry,
        model_provider: IModelProvider | None = None,
        termination: TerminationChain | None = None,
        default_settings: TurnSettings | None = None,
        context_manager: ContextManager | None = None,
        task_store: ITaskStore | None = None,
    ) -> None:
        self._model_provider = model_provider
        self._step_runner = StepRunner(executor, registry)
        self._termination = termination or TerminationChain()
        self._context_manager = context_manager or ContextManager()
        self._task_store = task_store
        self._default_settings = default_settings or TurnSettings(
            model="gpt-4o",
            system_prompt="You are a helpful agent.",
            budget=Budget(),
            tool_names=frozenset(),
        )

        # State for running tasks
        self._running: dict[str, AgentTask] = {}
        self._interrupt_flags: dict[str, asyncio.Event] = {}
        self._steering_queues: dict[str, asyncio.Queue[SteeringMessage]] = {}
        self._event_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    # ------------------------------------------------------------------
    # IOrchestrator implementation
    # ------------------------------------------------------------------

    async def run(self, task: AgentTask) -> AgentTask:
        """
        Drive the task loop until a termination condition fires.

        Loop structure:
            while not terminated:
                turn = start_turn(task)
                while not terminated:
                    apply pending steering (at safe checkpoint)
                    model_response = call_model(turn)
                    step = step_runner.run(turn, model_response)
                    turn.steps.append(step)
                    if termination_condition:
                        break
        """
        task.status = TaskStatus.RUNNING
        self._save(task)
        self._running[task.id] = task
        self._interrupt_flags[task.id] = asyncio.Event()
        self._steering_queues[task.id] = asyncio.Queue()

        try:
            await self._loop(task)
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
        except Exception as exc:
            task.context["error"] = str(exc)
            task.status = TaskStatus.FAILED
            await self._emit(task.id, {"type": "error", "error": str(exc)})
        finally:
            self._cleanup(task.id)

        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()

        self._save(task)
        await self._emit(task.id, {"type": "task_finished", "status": task.status})
        return task

    async def resume(self, task_id: str) -> AgentTask:
        """Resume a persisted task from its latest committed step."""
        task = self.load(task_id)
        if task is None:
            raise KeyError(f"Task '{task_id}' was not found")
        if task.status not in {TaskStatus.PAUSED, TaskStatus.FAILED}:
            raise ValueError(
                f"Task '{task_id}' cannot be resumed from status '{task.status.value}'"
            )
        task.status = TaskStatus.PENDING
        task.context.pop("error", None)
        return await self.run(task)

    async def interrupt(self, task_id: str) -> None:
        """Set the interrupt flag; the loop will pause at the next safe point."""
        if flag := self._interrupt_flags.get(task_id):
            flag.set()
        elif self._task_store and (task := self._task_store.get(task_id)):
            task.status = TaskStatus.PAUSED
            self._task_store.save(task)

    async def steer(self, task_id: str, message: SteeringMessage) -> None:
        """
        Queue a steering message for the running loop.

        Delivery is deferred to a safe checkpoint (after current tool
        chain completes) so in-flight steps are never orphaned.
        """
        if queue := self._steering_queues.get(task_id):
            await queue.put(message)

    def event_stream(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        """Return an async generator that yields events for this task."""
        return self._event_generator(task_id)

    # ------------------------------------------------------------------
    # Internal loop logic
    # ------------------------------------------------------------------

    async def _loop(self, task: AgentTask) -> None:
        last_step: Step | None = None

        while True:
            # Check interrupt or an approval pause before starting another turn.
            if task.status == TaskStatus.PAUSED:
                return
            if self._interrupt_flags[task.id].is_set():
                task.status = TaskStatus.PAUSED
                await self._emit(task.id, {"type": "paused"})
                return

            # Check termination before starting a new turn
            reason = self._termination.should_terminate(task, last_step)
            if reason is not None:
                await self._emit(task.id, {"type": "terminated", "reason": reason})
                return

            # Start a new turn with an immutable settings snapshot
            turn = self._start_turn(task)
            task.turns.append(turn)
            await self._emit(task.id, {"type": "turn_started", "turn_id": turn.id})

            last_step = await self._run_turn(task, turn)

    async def _run_turn(self, task: AgentTask, turn: Turn) -> Step | None:
        """Execute steps inside one turn until a condition fires."""
        last_step: Step | None = None

        while True:
            # Safe checkpoint: apply pending steering before next step
            steering_applied = await self._apply_steering(task, turn)

            # Check interrupt, approval pause, or termination.
            if self._interrupt_flags[task.id].is_set() or task.status == TaskStatus.PAUSED:
                return last_step
            reason = self._termination.should_terminate(task, last_step)
            # A steering message may arrive while the previous model call was
            # in flight.  If so, do not let a no-tool-calls response complete
            # the task before the new instruction is sent to the model.
            if reason is not None and steering_applied:
                reason = None
            if reason is not None:
                turn.finished_at = datetime.utcnow()
                return last_step

            # Build model request from turn history
            model_request = self._build_model_request(task, turn)
            if task.context.pop("context_compacted", False):
                await self._emit(task.id, {
                    "type": "context_compacted",
                    "turn_id": turn.id,
                    "budget": self._context_manager.budget.max_total_tokens,
                })
            await self._emit(task.id, {"type": "step_started", "turn_id": turn.id})

            # Call the injected model provider.
            model_response = await self._call_model(turn, model_request)

            # Execute any tool calls and build the Step
            step = await self._step_runner.run(
                turn=turn,
                model_request=model_request,
                model_response=model_response,
                tokens_used=model_response.get("usage", {}).get("total_tokens", 0),
            )
            turn.steps.append(step)
            last_step = step
            if any(obs.metadata.get("approval_required") for obs in step.observations):
                task.status = TaskStatus.PAUSED
                task.context["pause_reason"] = "approval_required"
            self._save(task)

            await self._emit(task.id, {
                "type": "step_completed",
                "turn_id": turn.id,
                "step_id": step.id,
                "tool_calls": len(step.tool_calls),
            })

        return last_step  # unreachable — kept for type checker

    def _start_turn(self, task: AgentTask) -> Turn:
        """Create a new Turn with a frozen settings snapshot."""
        return Turn(
            id=str(uuid.uuid4()),
            task_id=task.id,
            settings_snapshot=self._default_settings,
            started_at=datetime.utcnow(),
        )

    def _build_model_request(self, task: AgentTask, turn: Turn) -> dict[str, Any]:
        """
        Assemble the messages list from task history.

        In a full implementation this is where context compression
        and per-modality token budgets would be applied.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": turn.settings_snapshot.system_prompt},
            {"role": "user", "content": task.goal},
        ]

        if turn.user_input:
            messages.append({"role": "user", "content": turn.user_input})

        # Re-inject prior step responses, tool calls, and observations.
        for t in task.turns:
            for step in t.steps:
                # Prefer the provider's verbatim message: providers may require
                # fields back that our normalized shape drops or re-encodes.
                # Falls back to reconstruction for providers that omit it.
                raw_message = step.model_response.get("raw_message")
                if raw_message:
                    messages.append(raw_message)
                else:
                    assistant_message: dict[str, Any] = {
                        "role": "assistant",
                        "content": step.model_response.get("content") or "",
                    }
                    if step.model_response.get("tool_calls"):
                        assistant_message["tool_calls"] = step.model_response["tool_calls"]
                    messages.append(assistant_message)
                for obs in step.observations:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": obs.call_id,
                        "content": obs.to_model_content(),
                    })

        messages, compacted = self._context_manager.build(messages)
        if compacted:
            # This is a normal loop branch, not an exceptional overflow path.
            # The event is emitted by _run_turn after this method returns.
            task.context["context_compacted"] = True

        return {
            "model": turn.settings_snapshot.model,
            "messages": messages,
            "tools": [
                s.to_openai_function()
                for s in self._step_runner._registry.list_schemas()
                if s.qualified_name in turn.settings_snapshot.tool_names
                or not turn.settings_snapshot.tool_names  # empty = all tools
            ],
        }

    async def _call_model(
        self, turn: Turn, request: dict[str, Any]
    ) -> dict[str, Any]:
        """
        The provider is injected to keep this loop provider-neutral.
        A missing provider is allowed for deterministic unit tests only.
        Production wiring should always provide DeepSeekProvider.
        """
        if self._model_provider is None:
            return {
                "content": "Task complete.",
                "tool_calls": [],
                "usage": {"total_tokens": 0},
            }
        return await self._model_provider.complete(request)

    async def _apply_steering(self, task: AgentTask, turn: Turn) -> bool:
        """
        Drain any pending steering messages into the turn's user input.

        Called at turn-boundary checkpoints to avoid interrupting an
        active tool chain mid-execution.
        """
        queue = self._steering_queues.get(task.id)
        if not queue:
            return False
        messages: list[str] = []
        while not queue.empty():
            msg = await queue.get()
            messages.append(msg.content)
        if messages and turn.user_input is not None:
            turn.user_input += "\n" + "\n".join(messages)
        elif messages:
            turn.user_input = "\n".join(messages)
        return bool(messages)

    # ------------------------------------------------------------------
    # Event streaming
    # ------------------------------------------------------------------

    async def _emit(self, task_id: str, event: dict[str, Any]) -> None:
        event.setdefault("task_id", task_id)
        event.setdefault("ts", datetime.utcnow().isoformat())
        for q in self._event_queues[task_id]:
            await q.put(event)

    async def _event_generator(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._event_queues[task_id].append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._event_queues[task_id].remove(q)

    def load(self, task_id: str) -> AgentTask | None:
        """Load the latest committed task snapshot for resume or inspection."""
        return self._task_store.get(task_id) if self._task_store else None

    def _save(self, task: AgentTask) -> None:
        if self._task_store is not None:
            self._task_store.save(task)

    def _cleanup(self, task_id: str) -> None:
        self._running.pop(task_id, None)
        self._interrupt_flags.pop(task_id, None)
        self._steering_queues.pop(task_id, None)
