import pytest


class RecordingExecutor:
    def __init__(self, label):
        self.label = label
        self.calls = []

    def execute(self, step, context, payload, helper=None):
        self.calls.append((self.label, step.name, payload))
        return step.action(context, payload)


@pytest.mark.unit
class TestExecutorSelection:
    def test_workflow_uses_provided_default_executor(self):
        from py_workflow import Step, Workflow

        default_executor = RecordingExecutor("workflow-default")

        workflow = Workflow(executor=default_executor).add(
            Step(
                name="one",
                action=lambda ctx, payload: payload + ["one"],
                decision=lambda ctx, result, enqueue: enqueue.tail("two", result.value),
            ),
            Step(
                name="two",
                action=lambda ctx, payload: payload + ["two"],
            ),
        )

        context, trace = workflow.run(start="one", payload=[])

        assert context["result.two"] == ["one", "two"]
        assert [call[0] for call in default_executor.calls] == [
            "workflow-default",
            "workflow-default",
        ]
        assert [entry["step"] for entry in trace] == ["one", "two"]

    def test_run_accepts_executor_override(self):
        from py_workflow import Step, Workflow

        default_executor = RecordingExecutor("workflow-default")
        override_executor = RecordingExecutor("override")

        workflow = Workflow(executor=default_executor).add(
            Step(
                name="one",
                action=lambda ctx, payload: payload + ["one"],
                decision=lambda ctx, result, enqueue: enqueue.tail("two", result.value),
            ),
            Step(name="two", action=lambda ctx, payload: payload + ["two"]),
        )

        workflow.run(start="one", payload=[], executor=override_executor)

        assert not default_executor.calls
        assert [call[0] for call in override_executor.calls] == [
            "override",
            "override",
        ]

    def test_step_executor_trumps_defaults(self):
        from py_workflow import Step, Workflow

        default_executor = RecordingExecutor("workflow-default")
        override_executor = RecordingExecutor("override")
        special_executor = RecordingExecutor("special")

        workflow = Workflow(executor=default_executor).add(
            Step(
                name="one",
                action=lambda ctx, payload: payload + ["one"],
                executor=special_executor,
                decision=lambda ctx, result, enqueue: enqueue.tail(
                    "two", result.value
                ),
            ),
            Step(name="two", action=lambda ctx, payload: payload + ["two"]),
        )

        workflow.run(start="one", payload=[], executor=override_executor)

        assert [call[0] for call in special_executor.calls] == ["special"]
        assert [call[0] for call in override_executor.calls] == ["override"]
        assert not default_executor.calls
