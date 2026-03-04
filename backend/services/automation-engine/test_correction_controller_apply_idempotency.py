from correction_controller_apply import build_correction_idempotency_key


def test_build_correction_idempotency_key_is_stable_for_same_input():
    key_1 = build_correction_idempotency_key(
        zone_id=2,
        correction_type_str="ph",
        correction_type="add_acid",
        current_val=6.72,
        target_val=5.75,
        diff=0.97,
        reason="policy_allowed",
        correlation_id="corr:correction:2:ph:abc123",
    )
    key_2 = build_correction_idempotency_key(
        zone_id=2,
        correction_type_str="ph",
        correction_type="add_acid",
        current_val=6.72,
        target_val=5.75,
        diff=0.97,
        reason="policy_allowed",
        correlation_id="corr:correction:2:ph:abc123",
    )

    assert key_1 == key_2


def test_build_correction_idempotency_key_changes_with_correlation_id():
    key_1 = build_correction_idempotency_key(
        zone_id=2,
        correction_type_str="ph",
        correction_type="add_acid",
        current_val=6.72,
        target_val=5.75,
        diff=0.97,
        reason="policy_allowed",
        correlation_id="corr:correction:2:ph:abc123",
    )
    key_2 = build_correction_idempotency_key(
        zone_id=2,
        correction_type_str="ph",
        correction_type="add_acid",
        current_val=6.72,
        target_val=5.75,
        diff=0.97,
        reason="policy_allowed",
        correlation_id="corr:correction:2:ph:def456",
    )

    assert key_1 != key_2
