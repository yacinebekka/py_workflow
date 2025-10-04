import pytest


@pytest.mark.unit
class TestWorkflowSafety:
    def test_unknown_start_step_raises_error(self):
        from py_workflow import Step, UnknownStep, Workflow

        workflow = Workflow().add(
            Step(name="known", action=lambda ctx, payload: None)
        )

        with pytest.raises(UnknownStep) as excinfo:
            workflow.run(start="missing")

        assert "missing" in str(excinfo.value)

    def test_duplicate_registration_is_rejected(self):
        from py_workflow import Step, Workflow

        workflow = Workflow()
        workflow.add(Step(name="duplicate", action=lambda ctx, payload: None))

        with pytest.raises(ValueError) as excinfo:
            workflow.add(
                Step(name="duplicate", action=lambda ctx, payload: None)
            )

        assert "duplicate" in str(excinfo.value)

    def test_step_limit_enforced(self):
        from py_workflow import Step, StepLimitExceeded, Workflow

        workflow = Workflow().add(
            Step(
                name="loop",
                action=lambda ctx, payload: None,
                decision=lambda ctx, result, enqueue: enqueue.tail("loop"),
            )
        )

        with pytest.raises(StepLimitExceeded):
            workflow.run(start="loop", max_steps=3)
