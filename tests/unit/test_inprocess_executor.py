import pytest


@pytest.mark.unit
class TestInProcessExecutor:
    def test_run_executes_workflow_and_returns_context_and_trace(self):
        from py_workflow import InProcessExecutor, Step, Workflow

        def start_action(ctx, payload):
            ctx.setdefault("log", []).append("start")
            return list(ctx["log"])

        def finish_action(ctx, payload):
            ctx["log"].append("finish")
            return list(ctx["log"])

        workflow = Workflow().add(
            Step(
                name="start",
                action=start_action,
                decision=lambda ctx, result, enqueue: enqueue.tail(
                    "finish", result.value
                ),
            ),
            Step(name="finish", action=finish_action),
        )

        executor = InProcessExecutor()

        context, trace = executor.run(
            workflow,
            start="start",
            payload=None,
            ctx={},
        )

        assert context["log"] == ["start", "finish"]
        assert context["result.finish"] == ["start", "finish"]
        assert [entry["step"] for entry in trace] == ["start", "finish"]
        assert all(entry["ok"] for entry in trace)

    def test_run_captures_errors_and_continues(self):
        from py_workflow import InProcessExecutor, Step, Workflow

        workflow = Workflow().add(
            Step(
                name="boom",
                action=lambda ctx, payload: (_ for _ in ()).throw(RuntimeError("fail")),
                decision=lambda ctx, result, enqueue: enqueue.tail("recover", "ok"),
            ),
            Step(
                name="recover",
                action=lambda ctx, payload: ctx.setdefault("recovered", payload),
            ),
        )

        executor = InProcessExecutor()

        context, trace = executor.run(workflow, start="boom")

        assert context["recovered"] == "ok"
        assert context["result.boom"] is None
        assert [entry["ok"] for entry in trace] == [False, True]
        assert "fail" in trace[0]["error"]

    def test_steps_delegate_to_custom_executors(self):
        from py_workflow import Step, Workflow

        class RecordingExecutor:
            def __init__(self, label):
                self.label = label
                self.calls = []

            def execute(self, step, context, payload):
                self.calls.append((self.label, step.name, payload))
                return step.action(context, payload)

        prepare_executor = RecordingExecutor("prepare")
        finalize_executor = RecordingExecutor("finalize")

        workflow = Workflow().add(
            Step(
                name="prepare",
                action=lambda ctx, payload: {"value": payload},
                decision=lambda ctx, result, enqueue: enqueue.tail(
                    "finalize", result.value
                ),
                executor=prepare_executor,
            ),
            Step(
                name="finalize",
                action=lambda ctx, payload: ctx.setdefault("seen", payload["value"]),
                executor=finalize_executor,
            ),
        )

        context, trace = workflow.run(start="prepare", payload="data")

        assert context["seen"] == "data"
        assert [entry["step"] for entry in trace] == ["prepare", "finalize"]
        assert prepare_executor.calls == [("prepare", "prepare", "data")]
        assert finalize_executor.calls == [
            ("finalize", "finalize", {"value": "data"})
        ]
