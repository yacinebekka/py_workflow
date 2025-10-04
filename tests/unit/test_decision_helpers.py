import pytest


@pytest.mark.unit
class TestDecideTo:
    def test_tail_enqueues_next_step_with_result_payload(self):
        from py_workflow import Step, Workflow, decide_to

        def finisher_action(ctx, payload):
            ctx["payload_seen"] = payload

        workflow = Workflow().add(
            Step(
                name="start",
                action=lambda ctx, payload: {"data": 42},
                decision=decide_to("finish"),
            ),
            Step(name="finish", action=finisher_action),
        )

        context, trace = workflow.run(start="start")

        assert context["payload_seen"] == {"data": 42}
        assert [entry["step"] for entry in trace] == ["start", "finish"]

    def test_head_runs_priority_step_before_tail(self):
        from py_workflow import Step, Workflow, decide_to

        def collector(ctx, payload):
            ctx.setdefault("order", []).append((payload, payload))

        head_decision = decide_to("priority", where="head")
        tail_decision = decide_to("normal")

        def start_decision(ctx, result, enqueue):
            head_decision(ctx, result, enqueue)
            tail_decision(ctx, result, enqueue)

        workflow = Workflow().add(
            Step(
                name="start",
                action=lambda ctx, payload: "payload",
                decision=start_decision,
            ),
            Step(name="priority", action=collector),
            Step(name="normal", action=collector),
        )

        context, trace = workflow.run(start="start")

        assert [entry["step"] for entry in trace] == [
            "start",
            "priority",
            "normal",
        ]
        assert context["order"] == [
            ("payload", "payload"),
            ("payload", "payload"),
        ]

    def test_invalid_where_raises(self):
        from py_workflow import decide_to

        with pytest.raises(ValueError):
            decide_to("next", where="middle")


@pytest.mark.unit
class TestDecideIf:
    def test_routes_yes_branch(self):
        from py_workflow import Step, Workflow, decide_if

        yes_calls = []

        def router_action(ctx, payload):
            return payload

        def yes_action(ctx, payload):
            yes_calls.append(payload)

        decision = decide_if(
            pred=lambda ctx, result: result.value == "yes",
            yes="yes_step",
            where_yes="head",
        )

        workflow = Workflow().add(
            Step(name="router", action=router_action, decision=decision),
            Step(name="yes_step", action=yes_action),
        )

        workflow.run(start="router", payload="yes")

        assert yes_calls == ["yes"]

    def test_routes_no_branch_when_provided(self):
        from py_workflow import Step, Workflow, decide_if

        calls = []

        def router_action(ctx, payload):
            return payload

        def record(ctx, payload):
            calls.append((ctx["route"], payload))

        decision = decide_if(
            pred=lambda ctx, result: ctx["route"] == "yes",
            yes="yes_step",
            no="no_step",
            where_no="tail",
        )

        workflow = Workflow().add(
            Step(name="router", action=router_action, decision=decision),
            Step(name="yes_step", action=record),
            Step(name="no_step", action=record),
        )

        workflow.run(start="router", payload="payload", ctx={"route": "no"})

        assert calls == [("no", "payload")]

    def test_no_branch_is_optional(self):
        from py_workflow import Step, Workflow, decide_if

        decision = decide_if(lambda ctx, result: False, yes="unused")

        workflow = Workflow().add(
            Step(name="router", action=lambda ctx, payload: None, decision=decision)
        )

        context, trace = workflow.run(start="router")

        assert context["result.router"] is None
        assert len(trace) == 1

    def test_invalid_where_arguments_raise(self):
        from py_workflow import decide_if

        with pytest.raises(ValueError):
            decide_if(lambda ctx, result: True, yes="x", where_yes="middle")
        with pytest.raises(ValueError):
            decide_if(lambda ctx, result: False, yes="x", no="y", where_no="middle")
