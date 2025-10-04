import pytest

from py_workflow import Step, Workflow


@pytest.mark.acceptance
class TestWorkflowExecution:
    def test_create_valid_workflow_executes_all_steps_successfully(self):
        """A happy-path workflow runs each queued step and returns a success summary."""
        workflow = Workflow(name="order-fulfillment").add(
            Step(
                name="load_work",
                action=self._load_work_action,
                decision=self._load_work_decision,
            ),
            Step(
                name="process_order",
                action=self._process_order_action,
                decision=self._process_order_decision,
            ),
            Step(
                name="finalize_batch",
                action=self._finalize_batch_action,
            ),
        )

        initial_payload = {"batch_id": "batch-42"}
        initial_context = {"batch_id": "batch-42", "events": []}

        context, trace = workflow.run(
            start="load_work",
            payload=initial_payload,
            ctx=initial_context,
        )

        assert context["handled_orders"] == [
            "priority-order",
            "regular-1",
            "regular-2",
        ]
        assert context["events"] == [
            "load-work",
            "processed:priority-order",
            "processed:regular-1",
            "processed:regular-2",
            "finalize",
        ]
        assert context["result.load_work"] == {
            "urgent": [
                {"order_id": "priority-order", "priority": "urgent"},
            ],
            "normal": [
                {"order_id": "regular-1", "priority": "normal"},
                {"order_id": "regular-2", "priority": "normal"},
            ],
        }
        assert context["result.process_order"] == {
            "order_id": "regular-2",
            "priority": "normal",
            "status": "processed",
        }
        assert context["result.finalize_batch"] == {
            "batch_id": "batch-42",
            "processed_orders": [
                "priority-order",
                "regular-1",
                "regular-2",
            ],
            "status": "completed",
        }

        executed_steps = [entry["step"] for entry in trace]
        assert executed_steps == [
            "load_work",
            "process_order",
            "process_order",
            "process_order",
            "finalize_batch",
        ]
        assert all(entry["ok"] for entry in trace)
        assert trace[1]["payload_in"] == {
            "order_id": "priority-order",
            "priority": "urgent",
        }
        assert trace[-1]["value"] == {
            "batch_id": "batch-42",
            "processed_orders": [
                "priority-order",
                "regular-1",
                "regular-2",
            ],
            "status": "completed",
        }

    def _load_work_action(self, context, payload):
        assert payload["batch_id"] == context["batch_id"]
        context.setdefault("events", []).append("load-work")
        return {
            "urgent": [
                {"order_id": "priority-order", "priority": "urgent"},
            ],
            "normal": [
                {"order_id": "regular-1", "priority": "normal"},
                {"order_id": "regular-2", "priority": "normal"},
            ],
        }

    def _load_work_decision(self, context, result, enqueue):
        assert result.ok is True

        for order in result.value["normal"]:
            enqueue.tail("process_order", order)

        for order in reversed(result.value["urgent"]):
            enqueue.head("process_order", order)

        enqueue.tail("finalize_batch", {"batch_id": context["batch_id"]})

    def _process_order_action(self, context, payload):
        context.setdefault("handled_orders", []).append(payload["order_id"])
        context.setdefault("events", []).append(f"processed:{payload['order_id']}")
        return {
            "order_id": payload["order_id"],
            "priority": payload["priority"],
            "status": "processed",
        }

    def _process_order_decision(self, context, result, enqueue):
        assert result.ok is True
        assert result.value["status"] == "processed"

    def _finalize_batch_action(self, context, payload):
        context.setdefault("events", []).append("finalize")
        return {
            "batch_id": payload["batch_id"],
            "processed_orders": list(context["handled_orders"]),
            "status": "completed",
        }
