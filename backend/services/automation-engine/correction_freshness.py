from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import logging

from common.utils.time import utcnow
from config.settings import get_settings
from common.alerts import create_alert, AlertSource, AlertCode
from common.db import create_zone_event

logger = logging.getLogger(__name__)


async def validate_freshness_or_skip(
    *,
    zone_id: int,
    metric_name: str,
    target_key: str,
    correction_type: str,
    current: Any,
    target: Any,
    telemetry_timestamps: Optional[Dict[str, Any]],
    freshness_check_failure_count: Dict[int, int],
    event_prefix: str,
) -> bool:
    freshness_check_passed = False
    freshness_check_error = None

    if telemetry_timestamps:
        metric_timestamp = telemetry_timestamps.get(metric_name) or telemetry_timestamps.get(target_key)
        if metric_timestamp:
            try:
                if isinstance(metric_timestamp, str):
                    updated_at = datetime.fromisoformat(metric_timestamp.replace("Z", "+00:00"))
                elif isinstance(metric_timestamp, datetime):
                    updated_at = metric_timestamp
                else:
                    updated_at = None

                if updated_at:
                    settings = get_settings()
                    max_age = timedelta(minutes=settings.TELEMETRY_MAX_AGE_MINUTES)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    elif updated_at.tzinfo != timezone.utc:
                        updated_at = updated_at.astimezone(timezone.utc)
                    age = utcnow() - updated_at

                    if age > max_age:
                        logger.warning(
                            f"Zone {zone_id}: {metric_name} data is too old ({age.total_seconds() / 60:.1f} minutes, "
                            f"max: {settings.TELEMETRY_MAX_AGE_MINUTES} minutes). Skipping correction to prevent blind dosing.",
                            extra={
                                "component": "correction_freshness",
                                "zone_id": zone_id,
                                "metric": metric_name,
                                "decision": "skip",
                                "reason_code": "telemetry_data_too_old",
                            },
                        )
                        await create_zone_event(
                            zone_id,
                            f"{event_prefix}_CORRECTION_SKIPPED_STALE_DATA",
                            {
                                f"current_{target_key}": current,
                                f"target_{target_key}": target,
                                "data_age_minutes": age.total_seconds() / 60,
                                "max_age_minutes": settings.TELEMETRY_MAX_AGE_MINUTES,
                                "updated_at": metric_timestamp.isoformat() if isinstance(metric_timestamp, datetime) else str(metric_timestamp),
                                "reason": "telemetry_data_too_old",
                            },
                        )
                        freshness_check_failure_count.pop(zone_id, None)
                        return False
                    freshness_check_passed = True
                else:
                    freshness_check_error = "unable_to_parse_timestamp"
            except Exception as exc:
                freshness_check_error = str(exc)
        else:
            freshness_check_error = "timestamp_missing"
    else:
        freshness_check_error = "telemetry_timestamps_missing"

    if not freshness_check_passed:
        failure_count = freshness_check_failure_count.get(zone_id, 0) + 1
        freshness_check_failure_count[zone_id] = failure_count

        logger.warning(
            f"Zone {zone_id}: Failed to check {target_key} data freshness (error: {freshness_check_error}). "
            f"Skipping correction to prevent blind dosing (fail-closed). "
            f"Consecutive failures: {failure_count}",
            extra={
                "component": "correction_freshness",
                "zone_id": zone_id,
                "metric": metric_name,
                "decision": "skip",
                "reason_code": "freshness_check_failed",
                "error": freshness_check_error,
                "consecutive_failures": failure_count,
            },
        )

        await create_zone_event(
            zone_id,
            "CORRECTION_SKIPPED_FRESHNESS_CHECK_FAILED",
            {
                "correction_type": correction_type,
                "metric": metric_name,
                f"current_{target_key}": current,
                f"target_{target_key}": target,
                "error": freshness_check_error,
                "consecutive_failures": failure_count,
                "reason": "freshness_check_failed",
            },
        )

        settings = get_settings()
        if failure_count >= settings.FRESHNESS_CHECK_FAILED_ALERT_THRESHOLD:
            await create_alert(
                zone_id=zone_id,
                source=AlertSource.INFRA.value,
                code=AlertCode.INFRA_FRESHNESS_CHECK_FAILED.value,
                type="FRESHNESS_CHECK_FAILED",
                details={
                    "correction_type": correction_type,
                    "metric": metric_name,
                    "consecutive_failures": failure_count,
                    "error": freshness_check_error,
                    "threshold": settings.FRESHNESS_CHECK_FAILED_ALERT_THRESHOLD,
                },
            )

        return False

    freshness_check_failure_count.pop(zone_id, None)
    return True
