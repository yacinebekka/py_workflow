import pytest


@pytest.mark.unit
class TestWorkflowErrorHandling:
    def test_action_error_does_not_halt_queue(self):
        from py_workflow import Step, Workflow

        calls = []

        def boom(ctx, payload):
            raise RuntimeError("boom")

        def collector(ctx, payload):
            calls.append(payload)
            return "ok"

        workflow = Workflow().add(
            Step(
                name="first",
                action=boom,
                decision=lambda ctx, result, enqueue: enqueue.tail("second", "payload"),
            ),
            Step(name="second", action=collector),
        )

        context, trace = workflow.run(start="first")

        assert context["result.first"] is None
        assert context["result.second"] == "ok"
        assert calls == ["payload"]
        assert trace[0]["ok"] is False
        assert "boom" in trace[0]["error"]
        assert trace[1]["ok"] is True

    def test_unknown_step_enqueued_later_raises(self):
        from py_workflow import Step, UnknownStep, Workflow

        workflow = Workflow().add(
            Step(
                name="first",
                action=lambda ctx, payload: None,
                decision=lambda ctx, result, enqueue: enqueue.tail("missing"),
            )
        )

        with pytest.raises(UnknownStep) as excinfo:
            workflow.run(start="first")

        assert "missing" in str(excinfo.value)
