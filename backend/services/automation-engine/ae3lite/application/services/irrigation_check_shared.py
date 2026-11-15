"""Shared records and immutable policy values for IrrigationCheckHandler."""

from __future__ import annotations

import logging

_logger = logging.getLogger('ae3lite.application.handlers.irrigation_check')

_IRRIGATION_DURATION_MAX_SEC = 3600
