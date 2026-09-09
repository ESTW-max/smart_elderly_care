"""
Kernel interfaces - Abstract contracts following Dependency Inversion Principle.

All kernel components depend on these abstractions rather than concrete implementations.
"""

from app.kernel.interfaces.environment import IExecutionEnvironment
from app.kernel.interfaces.loop import IOrchestrator, ITerminationCondition
from app.kernel.interfaces.tool import ITool, IToolRegistry, IToolValidator

__all__ = [
    "IOrchestrator",
    "ITerminationCondition",
    "ITool",
    "IToolRegistry",
    "IToolValidator",
    "IExecutionEnvironment",
]
