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

    def event(self, step_name: str, name: str, **data: Any) -> None:
        ...


class StructuredLogger:
    def __init__(self, sink: LogSink):
        self._sink = sink

    def log(self, step_name: str, payload: Any, result: "Result") -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        error_repr = repr(result.error) if result.error else "None"
        fields = {
            "payload": repr(payload),
            "result": repr(result.value),
            "error": error_repr,
        }
        self._sink.write(self._format_line(timestamp, step_name, fields))

    def event(self, step_name: str, name: str, **data: Any) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        fields = {"event": name, **{key: repr(value) for key, value in data.items()}}
        self._sink.write(self._format_line(timestamp, step_name, fields))

    def _format_line(
        self, timestamp: str, step_name: str, fields: Dict[str, str]
    ) -> str:
        extras = " ".join(f"{key}={value}" for key, value in fields.items())
        suffix = f" {extras}" if extras else ""
        return f"timestamp={timestamp} step={step_name}{suffix}\n"


class BaseStepLogger:
    def log(self, step_name: str, payload: Any, result: "Result") -> None:  # pragma: no cover - default no-op
        raise NotImplementedError

    def event(self, step_name: str, name: str, **data: Any) -> None:  # pragma: no cover - default no-op
        # Default behaviour: ignore events unless overridden
        return


class StepLogHelper:
    def __init__(self, logger: StepLogger, step_name: str):
        self._logger = logger
        self._step_name = step_name

    def event(self, name: str, **data: Any) -> None:
        self._logger.event(self._step_name, name, **data)
