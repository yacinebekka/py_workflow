import pytest


class FakeExecutor:
    def __init__(self, label):
        self.label = label
        self.calls = []

    def execute(self, step, context, payload):
        self.calls.append((self.label, step.name, payload))
        return step.action(context, payload)


@pytest.mark.unit
class TestExecutorInterface:
    def test_workflow_delegates_to_step_executors(self):
        from py_workflow import Step, Workflow

        prepare_executor = FakeExecutor("prepare")
        finalize_executor = FakeExecutor("finalize")

        workflow = Workflow().add(
            Step(
                name="prepare",
                action=lambda ctx, payload: {"message": payload},
                decision=lambda ctx, result, enqueue: enqueue.tail(
                    "finalize", result.value
                ),
                executor=prepare_executor,
            ),
            Step(
                name="finalize",
                action=lambda ctx, payload: ctx.setdefault("messages", []).append(
                    payload["message"]
                ),
                executor=finalize_executor,
            ),
        )

        context, trace = workflow.run(
            start="prepare",
            payload="hello",
            ctx={"messages": []},
        )

        assert context["messages"] == ["hello"]
        assert [entry["step"] for entry in trace] == ["prepare", "finalize"]
        assert all(entry["ok"] for entry in trace)
        assert prepare_executor.calls == [("prepare", "prepare", "hello")]
        assert finalize_executor.calls == [
            ("finalize", "finalize", {"message": "hello"})
        ]

    def test_inprocess_executor_execute_runs_action(self):
        from py_workflow import Step
        from py_workflow.executors import InProcessExecutor

        executor = InProcessExecutor()

        def action(ctx, payload):
            ctx["seen"] = payload
            return "result"

        step = Step(name="act", action=action)
        context = {}

        outcome = executor.execute(step, context, payload="payload-data")

        assert context["seen"] == "payload-data"
        assert outcome == "result"
