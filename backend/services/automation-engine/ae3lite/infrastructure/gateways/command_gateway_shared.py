"""Shared records and immutable policy values for SequentialCommandGateway."""

from __future__ import annotations

import logging

logger = logging.getLogger('ae3lite.infrastructure.gateways.sequential_command_gateway')

_AE3_FAIL_SAFE_KEY = "_ae3_fail_safe"

_AE3_STAGE_EXECUTION_TOKEN_KEY = "_ae3_stage_execution_token"

_AE3_RECOVERY_RESUME_KEY = "_ae3_recovery_resume"

_PUMP_MAIN_CHANNEL = "pump_main"
