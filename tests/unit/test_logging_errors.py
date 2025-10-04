from io import StringIO
import re

import pytest

LOG_PATTERN = re.compile(
    r"timestamp=.* step=(?P<step>[^\s]+) payload=(?P<payload>.+) result=(?P<result>.+) error=(?P<error>.+)"
)


def _extract_steps_and_errors(buffer):
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    return [LOG_PATTERN.match(line).groupdict() for line in lines]


@pytest.mark.unit
class TestLoggingErrors:
    def test_error_and_retry_are_logged(self):
        from py_workflow import Step, Workflow

        buffer = StringIO()

        def unstable_action(ctx, payload):
            attempt = payload["attempt"]
            if attempt == 1:
                raise RuntimeError("boom")
            return {"status": "ok", "attempt": attempt}

        def unstable_decision(ctx, result, enqueue):
            if not result:
                next_attempt = ctx.setdefault("attempt", 1) + 1
                ctx["attempt"] = next_attempt
                enqueue.head("unstable", {"attempt": next_attempt})
            else:
                enqueue.tail("done", result.value)

        workflow = Workflow().add(
            Step(name="unstable", action=unstable_action, decision=unstable_decision),
            Step(name="done", action=lambda ctx, payload: payload),
        )

        context, trace = workflow.run(
            start="unstable",
            payload={"attempt": 1},
            logger_sink=buffer,
        )

        entries = _extract_steps_and_errors(buffer)
        assert [entry["step"] for entry in entries[:2]] == [
            "unstable",
            "unstable",
        ]
        assert entries[0]["error"].endswith("RuntimeError('boom')")
        assert entries[1]["error"] == "None"
        assert context["result.done"] == {"status": "ok", "attempt": 2}
        assert [entry["ok"] for entry in trace[:2]] == [False, True]
