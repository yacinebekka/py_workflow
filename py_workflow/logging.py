from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Result


class LogSink(Protocol):
    def write(self, message: str) -> Any:
        ...


class StepLogger(Protocol):
    def log(self, step_name: str, payload: Any, result: "Result") -> None:
        ...


class StructuredLogger:
    def __init__(self, sink: LogSink):
        self._sink = sink

    def log(self, step_name: str, payload: Any, result: "Result") -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        error_repr = repr(result.error) if result.error else "None"
        message = (
            f"timestamp={timestamp} step={step_name} "
            f"payload={repr(payload)} result={repr(result.value)} error={error_repr}\n"
        )
        self._sink.write(message)
