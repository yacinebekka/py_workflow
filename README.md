# py_workflow

`py_workflow` is a lightweight workflow engine. It lets you stitch
simple Python callables together into business-flavoured workflows with
pluggable executors, structured logging, retries, and decision-based routing.

## Installation

The project currently targets Python 3.12. Install it directly from the
repository (editable mode recommended while developing)::

    python -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -e .

### Development Dependencies

Running the tests requires `pytest`. Extra tools (coverage, formatters) are
optional but you can add them to your environment as needed.

    pip install -r requirements-dev.txt  # if you maintain one

## Quick Start

1. **Define steps** — each `Step` wraps an `action` plus an optional `decision`.
2. **Build a workflow** — register your steps with `Workflow.add()`.
3. **Execute** — call `workflow.run(...)`, optionally providing an executor and
   logging sink/helper.

```python
from io import StringIO
from py_workflow import Step, StructuredLogger, Workflow

def load(ctx, payload, log):
    log.event("start", payload=payload)
    return ["priority", "normal"]

def decide(ctx, result, enqueue, log):
    log.event("fanout", count=len(result.value))
    for item in result.value:
        enqueue.tail("process", item)

workflow = Workflow().add(
    Step(name="load", action=load, decision=decide),
    Step(name="process", action=lambda ctx, payload: payload.upper()),
)

buffer = StringIO()
context, trace = workflow.run(
    start="load",
    payload={"batch": "B-99"},
    logger=StructuredLogger(buffer),
)
```

### Logging

Every run can capture structured logs. The engine writes one line per step
execution plus any events your code emits via the helper.

```text
timestamp=2024-01-01T10:00:00+00:00 step=fetch event=start payload={'batch': 'B-1'}
timestamp=2024-01-01T10:00:00+00:00 step=fetch event=fanout count=2
timestamp=2024-01-01T10:00:00+00:00 step=fetch payload={'batch': 'B-1'} result=['A', 'B'] error=None
timestamp=2024-01-01T10:00:00+00:00 step=process event=processing item='A'
timestamp=2024-01-01T10:00:00+00:00 step=process payload='A' result='A_processed' error=None
```

- **Default step logs** capture payload, return value, and errors.
- **Helper events** — add a third `log` argument to actions and a fourth to
  decisions. The helper exposes `log.event(name, **details)` so you can emit
  arbitrary structured lines.
- **Sinks** — pass `logger_sink=<file-like>` for quick logging or supply a
  `StepLogger` (e.g., `StructuredLogger`) for richer formatting.

#### StepLogger protocol
This is the contract the workflow engine expects. A StepLogger must implement:
- log(step_name, payload, result): called once per step execution after the action finishes (success or failure). The Result object includes ok, value, and error.
- event(step_name, name, data): optional hook for helper-emitted events. 
If your logger doesn’t care about custom events, you can inherit from BaseStepLogger and leave the default no-op implementation.

#### StructuredLogger
This is the built-in implementation that writes plain-text structured lines (one per call) to a sink with a .write(str) method (file, stdout, StringIO, etc.). It produces two types of entries:
- Step results: timestamp=… step=… payload=… result=… error=…
  - payload is the inbound payload (repr form), result is the action return value, error is "None" for success or repr(exception) for failures.
- Custom events: timestamp=… step=… event=<name> key=value ...
Internally both funnels through format_line(...), so timestamp formatting and field ordering stay consistent.

#### StepLogHelper
For actions/decisions that accept an optional log argument, the engine instantiates StepLogHelper(logger, step_name) and passes it along. The helper currently exposes:
- event(name, data): convenience wrapper that calls the underlying logger’s event, prefixing the current step name. It handles loggers that lack an event method gracefully by doing nothing.
Because helper creation is per-step invocation, each event line is automatically tagged with the correct step name and timestamp once.

#### logger_sink vs logger
workflow.run takes two related parameters:
- logger_sink: any file-like sink. The engine wraps it in a StructuredLogger (default behaviour). Use this when you just want the plain text output.
- logger: a full StepLogger implementation (your own or a pre-built one). This bypasses the sink logic so you can emit JSON, send to an external monitoring service, etc.
You can pass both to get a StructuredLogger while also forwarding events to a custom logger, but usually you pick one.

#### Putting it together during execution

1. Workflow resolves step_logger once: custom logger > sink-based StructuredLogger > None.
2. When running a step:
    - Build a StepLogHelper if a logger exists.
    - Invoke the action through the executor, passing the helper if the callable accepts it.
    - Run the decision, again feeding the helper when requested.
    - Emit the standard result log via step_logger.log(...).
3. Any helper calls inside the action/decision (log.event(...)) are routed back through the same logger, so events and step results end up in the same stream.

#### Extending / customizing

- Custom format: implement StepLogger (or subclass BaseStepLogger) to produce JSON, send to logging.getLogger, etc.
- Additional events: just call log.event("foo", detail=...) wherever you need within an action/decision.
- No logging: omit both logger and logger_sink; nothing is written.

This design keeps logging pluggable and testable while offering a ready-to-use structured format out of the box.

### Executors

The default `InProcessExecutor` runs actions inline. You can inject a different
executor either at workflow construction (`Workflow(executor=...)`) or per-run
(`workflow.run(..., executor=...)`). Executors only execute **actions**; the
workflow continues to drive decisions, queueing, and logging.

## Recipe Book

### Logging with helper events

```python
from io import StringIO
from py_workflow import Step, StructuredLogger, Workflow

def fetch(ctx, payload, log):
    log.event("start", payload=payload)
    return {"items": [1, 2]}

def decide(ctx, result, enqueue, log):
    log.event("enqueue", size=len(result.value["items"]))
    for item in result.value["items"]:
        enqueue.tail("process", item)

def process(ctx, payload, log):
    log.event("processing", item=payload)
    return payload * 10

workflow = Workflow().add(
    Step(name="fetch", action=fetch, decision=decide),
    Step(name="process", action=process),
)

buffer = StringIO()
workflow.run(start="fetch", payload={"batch": "B-1"}, logger=StructuredLogger(buffer))
print(buffer.getvalue())
```

### Retry step

```python
from py_workflow import Step, Workflow

def attempt(ctx, payload, log):
    attempt_no = payload["attempt"]
    log.event("attempt", number=attempt_no)
    if attempt_no == 1:
        raise RuntimeError("transient")
    return {"status": "ok", "attempt": attempt_no}

def decide(ctx, result, enqueue, log):
    if not result:
        next_attempt = result.error.args[0] if False else payload["attempt"] + 1
        enqueue.head("attempt", {"attempt": next_attempt})
        log.event("retry", next_attempt=next_attempt)
    else:
        enqueue.tail("finalize", result.value)

def finalize(ctx, payload, log):
    log.event("final", payload=payload)
    ctx["final"] = payload

workflow = Workflow().add(
    Step(name="attempt", action=attempt, decision=decide),
    Step(name="finalize", action=finalize),
)
workflow.run(start="attempt", payload={"attempt": 1})
```

### Fan-out then merge

The acceptance spec `test_workflow_with_retry_and_merge` shows a full example
that fans out urgent/normal work, retries a failing item, collects results, and
finalizes. Refer to `tests/acceptance/test_workflow_success.py` for the full
listing.

### Structured logging to stdout

```python
import sys
workflow.run(..., logger_sink=sys.stdout)
```

### Custom logger

Subclass `BaseStepLogger` or implement `StepLogger` to route logs to your own
observability pipeline:

```python
from py_workflow import BaseStepLogger

class JSONLogger(BaseStepLogger):
    def __init__(self, sink):
        self._sink = sink

    def log(self, step_name, payload, result):
        self._sink.write(json.dumps({...}))

    def event(self, step_name, name, **data):
        self._sink.write(json.dumps({...}))

workflow.run(..., logger=JSONLogger(sys.stdout))
```

## Test Suite

| Test File | Behaviour |
| --- | --- |
| `tests/acceptance/test_workflow_success.py` | Happy-path workflow execution, retry/merge flow, structured logging, helper events |
| `tests/unit/test_executor_selection.py` | Executor precedence (workflow default, per-run override, per-step executors) |
| `tests/unit/test_inprocess_executor.py` | In-process executor semantics and helper compatibility |
| `tests/unit/test_logging_sinks.py` | Logging to `StringIO`, file sinks, and stdout |
| `tests/unit/test_logging_helper_contract.py` | Helper availability in actions/decisions, event emission, error handling |
| `tests/unit/test_logging_errors.py` | Logging for failing/retrying steps |
| `tests/unit/test_workflow_retry.py` | Retry mechanics in the core engine |
| `tests/unit/test_workflow_errors.py` | Error propagation without halting the queue |
| `tests/unit/test_safety_checks.py` | Guards against unknown steps, duplicates, and step limits |
| `tests/unit/test_decision_helpers.py` | `decide_to`/`decide_if` helper routing |


## License

MIT License (see `LICENSE`).
