"""
Agent Kernel - Core orchestration framework for autonomous agents.

This module provides the skeleton layer capabilities:
- Orchestration Loop: sampling → decision → action → observation cycle
- Tool Invocation: translating model intents to executable actions
- Execution Environment: abstraction for command execution and file operations

Architecture follows SOLID principles with clean separation between
interfaces and implementations.
"""

from app.kernel.interfaces.environment import IExecutionEnvironment
from app.kernel.interfaces.loop import IOrchestrator, ITerminationCondition
from app.kernel.interfaces.tool import ITool, IToolRegistry
from app.kernel.model.interfaces import IModelProvider

__all__ = [
    "IOrchestrator",
    "ITerminationCondition",
    "ITool",
    "IToolRegistry",
    "IExecutionEnvironment",
    "IModelProvider",
]
