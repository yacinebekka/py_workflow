import pytest


@pytest.mark.unit
class TestWorkflowRetries:
    def test_step_can_retry_itself_then_continue(self):
        from py_workflow import Step, Workflow

        def retry_action(ctx, payload):
            attempt = payload["attempt"]
            ctx.setdefault("attempts", []).append(attempt)
            if attempt == 1:
                raise RuntimeError("transient boom")
            return {"status": "ok", "attempt": attempt}

        def retry_decision(ctx, result, enqueue):
            if not result:
                enqueue.head("retry", {"attempt": ctx["attempts"][-1] + 1})
            else:
                enqueue.tail("finalize", result.value)

        workflow = Workflow().add(
            Step(
                name="retry",
                action=retry_action,
                decision=retry_decision,
            ),
            Step(
                name="finalize",
                action=lambda ctx, payload: ctx.setdefault("finalized", payload),
            ),
        )

        context, trace = workflow.run(start="retry", payload={"attempt": 1})

        assert context["attempts"] == [1, 2]
        assert context["finalized"] == {"status": "ok", "attempt": 2}
        assert [entry["step"] for entry in trace] == [
            "retry",
            "retry",
            "finalize",
        ]
        assert [entry["ok"] for entry in trace] == [False, True, True]
        assert "transient boom" in trace[0]["error"]
