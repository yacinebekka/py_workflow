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

        executor = self._make_executor()

        context, trace = executor.run(
            workflow,
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

    def test_workflow_with_retry_and_merge(self):
        workflow = Workflow(name="retry-flow").add(
            Step(
                name="load_orders",
                action=self._retry_load_orders_action,
                decision=self._retry_load_orders_decision,
            ),
            Step(
                name="process_order",
                action=self._retry_process_order_action,
                decision=self._retry_process_order_decision,
            ),
            Step(
                name="collect_order",
                action=self._retry_collect_order_action,
                decision=self._retry_collect_order_decision,
            ),
            Step(
                name="finalize_batch",
                action=self._retry_finalize_batch_action,
            ),
        )

        executor = self._make_executor()

        context, trace = executor.run(
            workflow,
            start="load_orders",
            payload={"batch_id": "B-99"},
            ctx={"events": []},
        )

        assert context["attempt_log"]["requires-retry"] == [1, 2]
        assert context["attempt_log"]["priority-first"] == [1]
        assert context["attempt_log"]["normal-done"] == [1]
        assert context["collected_orders"] == [
            {
                "order_id": "priority-first",
                "attempt": 1,
                "status": "processed",
            },
            {
                "order_id": "requires-retry",
                "attempt": 2,
                "status": "processed",
            },
            {
                "order_id": "normal-done",
                "attempt": 1,
                "status": "processed",
            },
        ]
        assert context["result.finalize_batch"] == {
            "batch_id": "B-99",
            "total_orders": 3,
            "processed_order_ids": [
                "priority-first",
                "requires-retry",
                "normal-done",
            ],
            "attempt_log": {
                "priority-first": [1],
                "requires-retry": [1, 2],
                "normal-done": [1],
            },
        }

        assert [entry["step"] for entry in trace] == [
            "load_orders",
            "process_order",
            "collect_order",
            "process_order",
            "process_order",
            "collect_order",
            "process_order",
            "collect_order",
            "finalize_batch",
        ]
        assert [entry["ok"] for entry in trace] == [
            True,
            True,
            True,
            False,
            True,
            True,
            True,
            True,
            True,
        ]
        assert "retry needed" in trace[3]["error"]
        assert trace[-1]["value"] == {
            "batch_id": "B-99",
            "total_orders": 3,
            "processed_order_ids": [
                "priority-first",
                "requires-retry",
                "normal-done",
            ],
            "attempt_log": {
                "priority-first": [1],
                "requires-retry": [1, 2],
                "normal-done": [1],
            },
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

    # === Helpers for retry/merge workflow ===

    def _retry_load_orders_action(self, context, payload):
        context["batch_id"] = payload["batch_id"]
        context["total_orders"] = 3
        context.setdefault("attempt_log", {})
        context.setdefault("events", []).append("load-orders")
        return {
            "priority": [
                {
                    "order_id": "priority-first",
                    "requires_retry": False,
                },
            ],
            "normal": [
                {
                    "order_id": "requires-retry",
                    "requires_retry": True,
                },
                {
                    "order_id": "normal-done",
                    "requires_retry": False,
                },
            ],
        }

    def _retry_load_orders_decision(self, context, result, enqueue):
        assert result.ok is True

        for order in result.value["normal"]:
            enqueue.tail("process_order", {"order": order, "attempt": 1})

        for order in reversed(result.value["priority"]):
            enqueue.head("process_order", {"order": order, "attempt": 1})

    def _retry_process_order_action(self, context, payload):
        order = payload["order"]
        attempt = payload["attempt"]
        order_id = order["order_id"]

        attempts = context.setdefault("attempt_log", {}).setdefault(order_id, [])
        attempts.append(attempt)
        context.setdefault("events", []).append(
            f"process:{order_id}:attempt-{attempt}"
        )
        context["last_payload"] = payload

        if order["requires_retry"] and attempt == 1:
            raise RuntimeError(f"retry needed for {order_id}")

        return {
            "order_id": order_id,
            "attempt": attempt,
            "status": "processed",
        }

    def _retry_process_order_decision(self, context, result, enqueue):
        if not result:
            payload = context["last_payload"]
            enqueue.head(
                "process_order",
                {
                    "order": payload["order"],
                    "attempt": payload["attempt"] + 1,
                },
            )
            return

        enqueue.head("collect_order", result.value)

    def _retry_collect_order_action(self, context, payload):
        collected = context.setdefault("collected_orders", [])
        collected.append(payload)
        context.setdefault("events", []).append(
            f"collect:{payload['order_id']}"
        )
        return list(collected)

    def _retry_collect_order_decision(self, context, result, enqueue):
        if len(context.get("collected_orders", [])) == context.get("total_orders"):
            enqueue.tail(
                "finalize_batch",
                {
                    "batch_id": context["batch_id"],
                    "orders": list(context["collected_orders"]),
                    "attempt_log": context["attempt_log"],
                },
            )

    def _retry_finalize_batch_action(self, context, payload):
        context.setdefault("events", []).append("finalize")
        return {
            "batch_id": payload["batch_id"],
            "total_orders": len(payload["orders"]),
            "processed_order_ids": [
                order["order_id"] for order in payload["orders"]
            ],
            "attempt_log": payload["attempt_log"],
        }

    def _make_executor(self):
        from py_workflow import InProcessExecutor

        return InProcessExecutor()
