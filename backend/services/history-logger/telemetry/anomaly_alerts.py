"""Throttled anomaly alerts (raised / resolved) для telemetry pipeline.

Module state (``_anomaly_alert_last_sent`` / ``_anomaly_resolved_last_sent``)
остаётся локальным — alert throttling не нужен снаружи.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from common.infra_alerts import send_infra_alert, send_infra_resolved_alert

from .helpers import build_anomaly_throttle_key, effective_anomaly_throttle_sec

_anomaly_alert_last_sent: dict[str, float] = {}
_anomaly_resolved_last_sent: dict[str, float] = {}
_anomaly_resolved_throttle_sec = float(
    os.getenv("TELEMETRY_ANOMALY_RESOLVED_THROTTLE_SEC", "300")
)


async def emit_telemetry_anomaly_alert(
    *,
    code: str,
    message: str,
    zone_id: Optional[int] = None,
    gh_uid: Optional[str] = None,
    zone_uid: Optional[str] = None,
    node_uid: Optional[str] = None,
    channel: Optional[str] = None,
    metric_type: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    throttle_key = build_anomaly_throttle_key(
        code=code,
        gh_uid=gh_uid,
        zone_uid=zone_uid,
        node_uid=node_uid,
        channel=channel,
    )
    throttle_sec = effective_anomaly_throttle_sec(code)
    now = time.time()
    last_sent = _anomaly_alert_last_sent.get(throttle_key)
    if last_sent and (now - last_sent) < throttle_sec:
        return

    payload_details = dict(details) if isinstance(details, dict) else {}
    payload_details.update(
        {
            "gh_uid": gh_uid,
            "zone_uid": zone_uid,
            "node_uid": node_uid,
            "channel": channel,
            "metric_type": metric_type,
            "throttle_key": throttle_key,
            "throttle_sec": throttle_sec,
        }
    )
    payload_details = {k: v for k, v in payload_details.items() if v is not None}

    sent = await send_infra_alert(
        code=code,
        alert_type="Telemetry Anomaly",
        message=message,
        severity="warning",
        zone_id=zone_id,
        service="history-logger",
        component="telemetry_processing",
        node_uid=node_uid,
        channel=channel,
        details=payload_details,
    )
    if sent:
        _anomaly_alert_last_sent[throttle_key] = now


async def emit_telemetry_anomaly_resolved_alert(
    *,
    code: str,
    message: str,
    zone_id: int,
    gh_uid: Optional[str] = None,
    zone_uid: Optional[str] = None,
    node_uid: Optional[str] = None,
    channel: Optional[str] = None,
    metric_type: Optional[str] = None,
) -> None:
    throttle_key = "|".join(
        [
            "resolved",
            code,
            str(zone_id),
            node_uid or "-",
        ]
    )
    now = time.time()
    last_sent = _anomaly_resolved_last_sent.get(throttle_key)
    if last_sent and (now - last_sent) < _anomaly_resolved_throttle_sec:
        return

    details = {
        "gh_uid": gh_uid,
        "zone_uid": zone_uid,
        "node_uid": node_uid,
        "channel": channel,
        "metric_type": metric_type,
        "throttle_key": throttle_key,
        "throttle_sec": _anomaly_resolved_throttle_sec,
    }
    details = {k: v for k, v in details.items() if v is not None}

    sent = await send_infra_resolved_alert(
        code=code,
        alert_type="Telemetry Anomaly",
        message=message,
        zone_id=zone_id,
        service="history-logger",
        component="telemetry_processing",
        node_uid=node_uid,
        channel=channel,
        details=details,
    )
    if sent:
        _anomaly_resolved_last_sent[throttle_key] = now
