from contextlib import redirect_stdout
from io import StringIO
import os
import re
import sys
import tempfile

import pytest


LOG_PATTERN = re.compile(
    r"^timestamp=(?P<ts>[^\s]+) step=(?P<step>[^\s]+) payload=(?P<payload>.+) result=(?P<result>.+) error=(?P<error>.+)$"
)


def _workflow_with_two_steps():
    from py_workflow import Step, Workflow

    return Workflow(name="logging-test").add(
        Step(
            name="first",
            action=lambda ctx, payload: payload + ["first"],
            decision=lambda ctx, result, enqueue: enqueue.tail(
                "second", result.value
            ),
        ),
        Step(
            name="second",
            action=lambda ctx, payload: payload + ["second"],
        ),
    )


@pytest.mark.unit
class TestLoggingSinks:
    def test_stringio_sink_collects_logs(self):
        workflow = _workflow_with_two_steps()
        buffer = StringIO()

        workflow.run(start="first", payload=[], logger_sink=buffer)

        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        assert [LOG_PATTERN.match(line).group("step") for line in lines] == [
            "first",
            "second",
        ]

    def test_file_sink_receives_entries(self):
        workflow = _workflow_with_two_steps()

        with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
            path = tmp.name
            workflow.run(start="first", payload=[], logger_sink=tmp)

        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = [line.strip() for line in fh.readlines() if line.strip()]
        finally:
            os.unlink(path)

        assert [LOG_PATTERN.match(line).group("step") for line in lines] == [
            "first",
            "second",
        ]

    def test_stdout_sink_can_be_used(self):
        workflow = _workflow_with_two_steps()
        buffer = StringIO()

        with redirect_stdout(buffer):
            workflow.run(start="first", payload=[], logger_sink=sys.stdout)

        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        assert [LOG_PATTERN.match(line).group("step") for line in lines] == [
            "first",
            "second",
        ]
