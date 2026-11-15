"""Pure classification of incomplete EC batches; no logging or stage transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PartialEcFailure:
    failed_index: int
    successful_components: list[str]
    failed_component: str
    remaining_components: list[str]
    failed_item: Mapping[str, Any]


def _component_name(item: Mapping[str, Any] | None, *, index: int) -> str:
    if not isinstance(item, Mapping):
        return f"step_{index}"
    name = str(item.get("component") or "").strip().lower()
    if name:
        return name
    node = str(item.get("node_uid") or "").strip()
    channel = str(item.get("channel") or "").strip()
    if node and channel:
        return f"{node}/{channel}"
    return f"step_{index}"


def first_failed_ec_index(
    *,
    seq: Sequence[Mapping[str, Any]],
    batch_result: Mapping[str, Any] | None,
) -> int:
    """Best-effort index of the first failed command in a parallel batch."""
    if not batch_result:
        return 0
    statuses = batch_result.get("command_statuses")
    if not isinstance(statuses, list) or not statuses:
        return 0
    for idx, status in enumerate(statuses):
        if not isinstance(status, Mapping):
            continue
        terminal = str(status.get("terminal_status") or "").strip().upper()
        if terminal and terminal != "DONE":
            return min(idx, max(0, len(seq) - 1))
        if status.get("success") is False:
            return min(idx, max(0, len(seq) - 1))
    # Gateway stops on first failure; statuses length often equals failed index + 1.
    if len(statuses) > 0:
        return min(len(statuses) - 1, max(0, len(seq) - 1))
    return 0


def describe_partial_ec_failure(
    *,
    seq: Sequence[Mapping[str, Any]],
    mode: str,
    failed_index: int,
    error_code: str,
    batch_result: Mapping[str, Any] | None,
) -> PartialEcFailure | None:
    # Stage-bound poll deadline must escalate to stage interrupt, not
    # partial-EC degrade (which would keep the correction window open).
    if str(error_code or "").strip().lower() == "ae3_command_poll_deadline_exceeded":
        return None
    if not seq:
        return None
    idx = int(failed_index)
    if idx < 0:
        idx = 0
    if idx >= len(seq):
        idx = len(seq) - 1

    # Partial = at least one prior component already dosed successfully.
    # For sequential: ec_current_seq_index / failed_index > 0.
    # For parallel: gateway may have completed earlier commands in the same batch.
    prior_success = idx > 0
    if mode == "multi_parallel" and batch_result is not None:
        statuses = batch_result.get("command_statuses")
        if isinstance(statuses, list):
            done_count = 0
            for status in statuses:
                if not isinstance(status, Mapping):
                    continue
                terminal = str(status.get("terminal_status") or "").strip().upper()
                if terminal == "DONE" or status.get("success") is True:
                    done_count += 1
            prior_success = done_count > 0 and idx > 0
    if not prior_success:
        return None

    successful = [_component_name(seq[i], index=i) for i in range(idx)]
    failed_item = seq[idx] if isinstance(seq[idx], Mapping) else {}
    failed_component = _component_name(failed_item, index=idx)
    remaining = [_component_name(seq[i], index=i) for i in range(idx + 1, len(seq))]

    return PartialEcFailure(
        failed_index=idx,
        successful_components=successful,
        failed_component=failed_component,
        remaining_components=remaining,
        failed_item=failed_item,
    )
