from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .executors import Executor, InProcessExecutor

Action = Callable[[Dict[str, Any], Any], Any]
Decision = Callable[[Dict[str, Any], "Result", "Enqueue"], None]


@dataclass
class Result:
    ok: bool
    value: Any = None
    error: Optional[BaseException] = None

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class Step:
    name: str
    action: Action
    decision: Optional[Decision] = None
    executor: Optional[Executor] = None


@dataclass
class Token:
    step: str
    payload: Any


class Enqueue:
    def __init__(self, q: Deque[Token], default_payload: Any):
        self._q = q
        self._default_payload = default_payload

    def head(self, step: str, payload: Any = None) -> None:
        self._q.appendleft(Token(step, self._pick(payload)))

    def tail(self, step: str, payload: Any = None) -> None:
        self._q.append(Token(step, self._pick(payload)))

    def _pick(self, payload: Any) -> Any:
        return self._default_payload if payload is None else payload


class UnknownStep(Exception):
    pass


class StepLimitExceeded(Exception):
    pass


def decide_to(step_name: str, *, where: str = "tail") -> Decision:
    if where not in {"head", "tail"}:
        raise ValueError("where must be 'head' or 'tail'")

    def _decision(ctx: Dict[str, Any], result: Result, enqueue: Enqueue) -> None:
        dispatcher = enqueue.head if where == "head" else enqueue.tail
        dispatcher(step_name)

    return _decision


def decide_if(
    pred: Callable[[Dict[str, Any], Result], bool],
    *,
    yes: str,
    no: Optional[str] = None,
    where_yes: str = "tail",
    where_no: str = "tail",
) -> Decision:
    if where_yes not in {"head", "tail"}:
        raise ValueError("where_yes must be 'head' or 'tail'")
    if where_no not in {"head", "tail"}:
        raise ValueError("where_no must be 'head' or 'tail'")

    def _decision(ctx: Dict[str, Any], result: Result, enqueue: Enqueue) -> None:
        if pred(ctx, result):
            dispatcher = enqueue.head if where_yes == "head" else enqueue.tail
            dispatcher(yes)
        elif no is not None:
            dispatcher = enqueue.head if where_no == "head" else enqueue.tail
            dispatcher(no)

    return _decision


class Workflow:
    def __init__(
        self,
        *,
        name: str = "workflow",
        executor: Optional[Executor] = None,
    ) -> None:
        self.name = name
        self._steps: Dict[str, Step] = {}
        self._default_executor: Executor = executor or InProcessExecutor()

    def add(self, *steps: Step) -> "Workflow":
        for step in steps:
            if step.name in self._steps:
                raise ValueError(f"Duplicate step: {step.name}")
            self._steps[step.name] = step
        return self

    def _require_step(self, name: str) -> Step:
        try:
            return self._steps[name]
        except KeyError as exc:  # pragma: no cover - exercised via public API
            raise UnknownStep(name) from exc

    def _execute_step(
        self,
        step: Step,
        context: Dict[str, Any],
        payload: Any,
        default_executor: Executor,
    ) -> Result:
        executor = self._resolve_executor(step, default_executor)
        try:
            value = executor.execute(step, context, payload)
            return Result(ok=True, value=value)
        except BaseException as exc:  # pragma: no cover
            return Result(ok=False, value=None, error=exc)

    def _store_result(
        self, context: Dict[str, Any], step_name: str, result: Result
    ) -> None:
        context[f"result.{step_name}"] = result.value if result.ok else None

    def _resolve_executor(
        self, step: Step, default_executor: Executor
    ) -> Executor:
        return step.executor or default_executor

    def _trace_entry(
        self,
        step_name: str,
        token: Token,
        result: Result,
        queue: Deque[Token],
    ) -> Dict[str, Any]:
        return {
            "step": step_name,
            "ok": result.ok,
            "payload_in": token.payload,
            "value": result.value,
            "error": repr(result.error) if result.error else None,
            "queue_len_after": len(queue),
        }

    def run(
        self,
        start: str,
        payload: Any = None,
        *,
        ctx: Optional[Dict[str, Any]] = None,
        max_steps: int = 10000,
        capture_trace: bool = True,
        executor: Optional[Executor] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        if start not in self._steps:
            raise UnknownStep(start)

        context: Dict[str, Any] = dict(ctx or {})
        queue: Deque[Token] = deque([Token(start, payload)])
        trace: List[Dict[str, Any]] = []
        steps_run = 0
        default_executor = executor or self._default_executor

        while queue:
            if steps_run >= max_steps:
                raise StepLimitExceeded(
                    f"Exceeded {max_steps} step executions; possible loop?"
                )

            token = queue.popleft()
            step = self._require_step(token.step)
            result = self._execute_step(
                step,
                context,
                token.payload,
                default_executor,
            )

            enqueue = Enqueue(queue, default_payload=result.value)
            if step.decision:
                step.decision(context, result, enqueue)

            self._store_result(context, step.name, result)

            if capture_trace:
                trace.append(self._trace_entry(step.name, token, result, queue))

            steps_run += 1

        return context, trace
