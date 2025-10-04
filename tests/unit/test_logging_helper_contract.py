from io import StringIO
import re

import pytest

LOG_PATTERN = re.compile(
    r"timestamp=.* step=(?P<step>[^\s]+) event=(?P<event>[^\s]+)(?P<data>.*)"
)
RESULT_PATTERN = re.compile(
    r"timestamp=.* step=(?P<step>[^\s]+) payload=(?P<payload>.+) result=(?P<result>.+) error=(?P<error>.+)"
)


@pytest.mark.unit
class TestLoggingHelperContract:
    def test_action_and_decision_receive_helper(self):
        from py_workflow import Step, StructuredLogger, Workflow

        buffer = StringIO()
        logger = StructuredLogger(buffer)

        emitted = []

        def action(ctx, payload, log):
            log.event("action-start", payload=payload)
            emitted.append("action")
            return payload + [1]

        def decision(ctx, result, enqueue, log):
            log.event("decision", size=len(result.value))
            emitted.append("decision")
            enqueue.tail("next", result.value)

        workflow = Workflow().add(
            Step(name="step", action=action, decision=decision),
            Step(name="next", action=lambda ctx, payload: payload),
        )

        workflow.run(start="step", payload=[], logger=logger)

        lines = [line.strip() for line in buffer.getvalue().splitlines() if line.strip()]
        action_event = LOG_PATTERN.match(lines[0]).groupdict()
        decision_event = LOG_PATTERN.match(lines[1]).groupdict()
        result_line = RESULT_PATTERN.match(lines[2]).groupdict()

        assert emitted == ["action", "decision"]
        assert action_event == {
            "step": "step",
            "event": "action-start",
            "data": " payload=[]",
        }
        assert decision_event == {
            "step": "step",
            "event": "decision",
            "data": " size=1",
        }
        assert result_line["step"] == "step"
        assert result_line["payload"] == "[]"
        assert result_line["result"] == "[1]"
        assert result_line["error"] == "None"

    def test_helper_handles_errors(self):
        from py_workflow import Step, StructuredLogger, Workflow

        buffer = StringIO()
        logger = StructuredLogger(buffer)

        def action(ctx, payload, log):
            log.event("about-to-error")
            raise RuntimeError("boom")

        workflow = Workflow().add(Step(name="err", action=action))

        workflow.run(start="err", payload=None, logger=logger)

        lines = [line.strip() for line in buffer.getvalue().splitlines() if line.strip()]
        assert len(lines) == 2
        event_line = LOG_PATTERN.match(lines[0]).groupdict()
        result_line = RESULT_PATTERN.match(lines[1]).groupdict()

        assert event_line["event"] == "about-to-error"
        assert result_line["step"] == "err"
        assert result_line["error"].endswith("RuntimeError('boom')")
