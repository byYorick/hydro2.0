import pytest

from correction_command_retry import (
    DEFAULT_COMPENSATION_TOPOLOGY,
    _resolve_duration_aware_timeout_sec,
    publish_controller_command_with_retry,
    trigger_ec_partial_batch_compensation,
)


@pytest.mark.asyncio
async def test_trigger_ec_partial_batch_compensation_uses_default_topology_when_missing():
    captured: dict = {}

    async def fake_enqueue_internal_scheduler_task(**kwargs):
        captured.update(kwargs)
        return {
            "enqueue_id": "enq-1",
            "task_type": kwargs.get("task_type"),
            "correlation_id": "corr-1",
        }

    async def fake_send_infra_alert(**kwargs):
        raise AssertionError(f"Unexpected alert: {kwargs}")

    result = await trigger_ec_partial_batch_compensation(
        zone_id=5,
        command={},
        successful_components=["npk"],
        failed_component="calcium",
        enqueue_internal_scheduler_task_fn=fake_enqueue_internal_scheduler_task,
        send_infra_alert_fn=fake_send_infra_alert,
    )

    assert result["status"] == "degraded_recovery_enqueued"
    assert captured["task_type"] == "diagnostics"
    payload = captured["payload"]
    assert payload["topology"] == DEFAULT_COMPENSATION_TOPOLOGY
    assert payload["workflow"] == "irrigation_recovery"
    assert payload["config"]["execution"]["topology"] == DEFAULT_COMPENSATION_TOPOLOGY
    assert payload["config"]["execution"]["workflow"] == "irrigation_recovery"


@pytest.mark.asyncio
async def test_trigger_ec_partial_batch_compensation_uses_topology_from_command():
    captured: dict = {}

    async def fake_enqueue_internal_scheduler_task(**kwargs):
        captured.update(kwargs)
        return {
            "enqueue_id": "enq-2",
            "task_type": kwargs.get("task_type"),
            "correlation_id": "corr-2",
        }

    async def fake_send_infra_alert(**kwargs):
        raise AssertionError(f"Unexpected alert: {kwargs}")

    result = await trigger_ec_partial_batch_compensation(
        zone_id=7,
        command={"topology": " THREE_TANK_DRIP_SUBSTRATE_TRAYS "},
        successful_components=["npk", "calcium"],
        failed_component="magnesium",
        enqueue_internal_scheduler_task_fn=fake_enqueue_internal_scheduler_task,
        send_infra_alert_fn=fake_send_infra_alert,
    )

    assert result["status"] == "degraded_recovery_enqueued"
    payload = captured["payload"]
    assert payload["topology"] == "three_tank_drip_substrate_trays"
    assert payload["config"]["execution"]["topology"] == "three_tank_drip_substrate_trays"


def test_duration_aware_timeout_prefers_command_duration_with_buffer():
    timeout = _resolve_duration_aware_timeout_sec(
        controller_command={"params": {"duration_ms": 9000}},
        base_timeout_sec=5.0,
        timeout_buffer_sec=2.0,
        min_timeout_sec=3.0,
    )
    assert timeout == 11.0


@pytest.mark.asyncio
async def test_publish_retry_treats_non_terminal_timeout_as_pending_success():
    class _FakeTracker:
        async def wait_for_command_done(self, **kwargs):
            _ = kwargs
            return None

        async def get_command_outcome(self, cmd_id):
            _ = cmd_id
            return {"status": "ACK", "error_code": None, "error_message": None}

    class _FakePublisher:
        def __init__(self):
            self.tracker = _FakeTracker()

        async def publish_controller_command(self, zone_id, controller_command, context):
            _ = zone_id, context
            controller_command["cmd_id"] = "cmd-ack-pending"
            return True

    class _Settings:
        CORRECTION_COMMAND_MAX_ATTEMPTS = 2
        CORRECTION_COMMAND_TIMEOUT_SEC = 1.0
        CORRECTION_COMMAND_TIMEOUT_BUFFER_SEC = 1.0
        CORRECTION_COMMAND_MIN_TIMEOUT_SEC = 1.0
        CORRECTION_COMMAND_RETRY_DELAY_SEC = 0.0

    events = []

    async def _create_zone_event(zone_id, event_type, payload):
        events.append((zone_id, event_type, payload))

    async def _send_infra_alert(**kwargs):
        raise AssertionError(f"Unexpected infra alert: {kwargs}")

    published = await publish_controller_command_with_retry(
        zone_id=9,
        command_gateway=_FakePublisher(),
        controller_command={
            "cmd": "run_pump",
            "params": {"duration_ms": 3000, "ml": 6.0},
            "node_uid": "nd-ec-a",
            "channel": "pump_a",
        },
        context={},
        correction_type="ec",
        get_settings_fn=lambda: _Settings(),
        create_zone_event_fn=_create_zone_event,
        send_infra_alert_fn=_send_infra_alert,
    )

    assert published is True
    assert any(event_type == "CORRECTION_COMMAND_PENDING_CONFIRMATION" for _, event_type, _ in events)
