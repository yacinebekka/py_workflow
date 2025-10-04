from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Step, Workflow


class Executor(Protocol):
    def execute(self, step: "Step", context: Dict[str, Any], payload: Any) -> Any:
        ...


class InProcessExecutor:
    def execute(self, step: "Step", context: Dict[str, Any], payload: Any) -> Any:
        return step.action(context, payload)

    def run(
        self,
        workflow: "Workflow",
        start: str,
        payload: Any = None,
        *,
        ctx: Optional[Dict[str, Any]] = None,
        max_steps: int = 10000,
        capture_trace: bool = True,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        return workflow.run(
            start=start,
            payload=payload,
            ctx=ctx,
            max_steps=max_steps,
            capture_trace=capture_trace,
            executor=self,
        )
