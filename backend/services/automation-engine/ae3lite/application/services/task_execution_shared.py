"""Shared records and immutable policy values for ExecuteTaskUseCase."""

from __future__ import annotations

import logging
import os

from ae3lite.domain.errors import (
    ErrorCodes,
)

logger = logging.getLogger('ae3lite.application.use_cases.execute_task')

TASK_EXECUTION_TIMEOUT_CANCEL_MSG = "ae3_task_execution_timeout"

TASK_EXECUTION_LEASE_LOST_CANCEL_MSG = "ae3_zone_lease_lost"

TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG = ErrorCodes.AE3_TASK_OVERALL_DEADLINE_EXCEEDED

NODE_STALE_ONLINE_THRESHOLD_SEC = max(1, int(os.getenv("NODE_OFFLINE_TIMEOUT_SEC", "120")))

SNAPSHOT_TRANSIENT_RETRY_SEC = max(1, int(os.getenv("AE3_SNAPSHOT_TRANSIENT_RETRY_SEC", "10")))

SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC = max(
    SNAPSHOT_TRANSIENT_RETRY_SEC,
    int(os.getenv("AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC", "600")),
)

NODE_PERSISTENT_DEAD_SEC = max(60, int(os.getenv("AE3_NODE_PERSISTENT_DEAD_SEC", "600")))

SNAPSHOT_RETRY_SCHEDULED_CODE = "infra_ae3_snapshot_retry_scheduled"

SNAPSHOT_RETRY_EXHAUSTED_CODE = "ae3_snapshot_retry_exhausted"

COMMAND_SEND_RETRY_SEC = max(1, int(os.getenv("AE3_COMMAND_SEND_RETRY_SEC", "8")))

COMMAND_SEND_MAX_STAGE_AGE_SEC = max(
    COMMAND_SEND_RETRY_SEC,
    int(os.getenv("AE3_COMMAND_SEND_MAX_STAGE_AGE_SEC", "120")),
)

COMMAND_SEND_RETRY_SCHEDULED_CODE = "infra_ae3_command_send_retry_scheduled"

COMMAND_SEND_RETRY_EXHAUSTED_CODE = "ae3_command_send_retry_exhausted"
