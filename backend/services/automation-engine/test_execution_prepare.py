"""Unit tests for application.execution_prepare helpers."""

from application.execution_prepare import prepare_execution_inputs


def test_prepare_execution_inputs_normalizes_and_resolves_mapping():
    marker = object()
    task_type, payload, mapping = prepare_execution_inputs(
        task_type="  Diagnostics  ",
        payload={"config": {"x": 1}, "k": "v"},
        get_task_mapping_fn=lambda tt, cfg: (tt, cfg, marker),
    )
    assert task_type == "diagnostics"
    assert payload["k"] == "v"
    assert mapping[0] == "diagnostics"
    assert mapping[1] == {"x": 1}
    assert mapping[2] is marker


def test_prepare_execution_inputs_handles_non_dict_payload():
    task_type, payload, mapping = prepare_execution_inputs(
        task_type="IRRIGATION",
        payload=None,  # type: ignore[arg-type]
        get_task_mapping_fn=lambda tt, cfg: {"task_type": tt, "config": cfg},
    )
    assert task_type == "irrigation"
    assert payload == {}
    assert mapping["config"] == {}
