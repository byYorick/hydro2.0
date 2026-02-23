from domain.policies.workflow_input_policy import (
    is_two_tank_startup_workflow,
    normalize_two_tank_workflow,
)


def test_normalize_two_tank_workflow_maps_cycle_start_to_startup():
    assert normalize_two_tank_workflow("cycle_start") == "startup"
    assert normalize_two_tank_workflow("CYCLE_START") == "startup"


def test_is_two_tank_startup_workflow_accepts_cycle_start_alias():
    assert is_two_tank_startup_workflow(
        topology="two_tank_drip_substrate_trays",
        workflow="cycle_start",
    )
