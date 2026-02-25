import pytest

from correction_command_retry import (
    DEFAULT_COMPENSATION_TOPOLOGY,
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
