"""Operator Agent package."""

from footstats.operator.manifest import CAPABILITIES
from footstats.operator.runner import RunResult, run_capability
from footstats.operator.workflow import OperatorWorkflow

__all__ = [
    "CAPABILITIES",
    "RunResult",
    "run_capability",
    "OperatorWorkflow",
]
