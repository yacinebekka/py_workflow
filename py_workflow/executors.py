from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Step
    from .logging import StepLogHelper

from ._callable_utils import call_with_optional_helper


class Executor(Protocol):
    def execute(
        self,
        step: "Step",
        context: Dict[str, Any],
        payload: Any,
        helper: Optional["StepLogHelper"] = None,
    ) -> Any:
        ...


class InProcessExecutor:
    def execute(
        self,
        step: "Step",
        context: Dict[str, Any],
        payload: Any,
        helper: Optional["StepLogHelper"] = None,
    ) -> Any:
        return call_with_optional_helper(
            step.action,
            (context, payload),
            helper,
            base_arg_count=2,
        )
