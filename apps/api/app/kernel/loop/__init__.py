"""
Loop layer - Concrete orchestration loop implementation.

Exports the orchestrator and built-in termination conditions so
callers can assemble an agent without importing sub-modules directly.
"""

from app.kernel.loop.orchestrator import Orchestrator
from app.kernel.loop.termination import (
    BudgetExhaustedCondition,
    ExternalSignalCondition,
    GoalReachedCondition,
    NoToolCallsCondition,
    TerminationChain,
)

__all__ = [
    "Orchestrator",
    "NoToolCallsCondition",
    "GoalReachedCondition",
    "BudgetExhaustedCondition",
    "ExternalSignalCondition",
    "TerminationChain",
]
