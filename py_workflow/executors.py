from __future__ import annotations

from typing import Any, Dict, Protocol, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Step


class Executor(Protocol):
    def execute(self, step: "Step", context: Dict[str, Any], payload: Any) -> Any:
        ...


class InProcessExecutor:
    def execute(self, step: "Step", context: Dict[str, Any], payload: Any) -> Any:
        return step.action(context, payload)
