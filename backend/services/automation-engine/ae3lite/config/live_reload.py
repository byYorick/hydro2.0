"""Live-mode hot-reload of zone config (Phase 5).

Reads the current zone bundle + active recipe phase directly from the DB,
bypassing the grow-cycle snapshot. Used by `BaseStageHandler._checkpoint()`
to refresh runtime spec mid-cycle when a zone is in `config_mode=live`.

Contract:
- Returns ``None`` when the zone is NOT in live mode, TTL is expired,
  or revision has not advanced past what the caller already holds.
- Returns a ``HotReloadResult`` when a fresh bundle is available.
- Never raises on normal "no-op" conditions; only raises on DB / parse
  errors (callers should log + keep current spec).

Database touchpoints:
- ``zones``: ``config_mode``, ``config_revision``, ``live_until``
- ``automation_effective_bundles``: current `zone` scope bundle
  (not the `grow_cycle` snapshot)
- ``grow_cycle_recipe_phases`` / ``recipe_phases``: active recipe phase
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.config.errors import ConfigLoaderError, ConfigValidationError
from ae3lite.config.loader import load_recipe_phase, load_zone_correction
from ae3lite.config.modes import ConfigMode
from ae3lite.config.schema.recipe_phase import RecipePhase
from ae3lite.config.schema.zone_correction import ZoneCorrection


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HotReloadResult:
    """Fresh live-mode spec loaded from the current bundle. Either field may
    be ``None`` if that namespace did not change — the caller should merge
    non-None parts into its runtime state.
    """

    zone_correction: ZoneCorrection | None
    recipe_phase: RecipePhase | None
    revision: int


async def refresh_if_changed(
    *,
    zone_id: int,
    current_revision: int,
    current_grow_cycle_id: int | None,
    conn: Any,
) -> HotReloadResult | None:
    """Return fresh spec when the zone is in live mode AND revision advanced.

    `conn` is an asyncpg ``Connection`` (same API used elsewhere in AE3).
    """
    row = await conn.fetchrow(
        """
        SELECT config_mode, config_revision, live_until
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    if row is None:
        return None

    mode = ConfigMode.parse(row.get("config_mode"))
    if mode is not ConfigMode.LIVE:
        return None

    live_until = row.get("live_until")
    if isinstance(live_until, datetime):
        now = datetime.now(timezone.utc)
        if live_until.tzinfo is None:
            # DB returned naive UTC — normalise to aware.
            live_until = live_until.replace(tzinfo=timezone.utc)
        if live_until < now:
            # TTL expired; Laravel cron will flip us to locked shortly.
            return None

    new_revision = int(row.get("config_revision") or 0)
    if new_revision <= current_revision:
        return None

    bundle_row = await conn.fetchrow(
        """
        SELECT config
        FROM automation_effective_bundles
        WHERE scope_type = 'zone'
          AND scope_id = $1
        LIMIT 1
        """,
        zone_id,
    )
    zone_correction: ZoneCorrection | None = None
    if bundle_row is not None and isinstance(bundle_row.get("config"), Mapping):
        zone_correction = _extract_zone_correction(bundle_row["config"], zone_id)

    recipe_phase: RecipePhase | None = None
    if current_grow_cycle_id is not None:
        recipe_phase = await _load_active_recipe_phase(
            conn=conn, grow_cycle_id=current_grow_cycle_id, zone_id=zone_id,
        )

    if zone_correction is None and recipe_phase is None:
        # Revision advanced but we could not fetch a usable namespace payload.
        # Treat as no-op rather than silently swap in partial state.
        _logger.warning(
            "live_reload: revision advanced but no namespace payload zone_id=%s rev=%s",
            zone_id, new_revision,
        )
        return None

    return HotReloadResult(
        zone_correction=zone_correction,
        recipe_phase=recipe_phase,
        revision=new_revision,
    )


def _extract_zone_correction(bundle_config: Mapping[str, Any], zone_id: int) -> ZoneCorrection | None:
    """Pick the zone's correction document out of an effective bundle config.

    Bundle layout (see `AutomationConfigCompiler`): `{system: {...}, zone: {correction: {...}}}`.
    """
    zone_block = bundle_config.get("zone") if isinstance(bundle_config.get("zone"), Mapping) else None
    if not isinstance(zone_block, Mapping):
        return None
    correction_doc = zone_block.get("correction")
    if not isinstance(correction_doc, Mapping):
        return None
    try:
        return load_zone_correction(correction_doc, zone_id=zone_id)
    except (ConfigValidationError, ConfigLoaderError) as exc:
        _logger.warning(
            "live_reload: zone_correction validation failed zone_id=%s err=%s",
            zone_id, exc,
        )
        return None


async def _load_active_recipe_phase(
    *,
    conn: Any,
    grow_cycle_id: int,
    zone_id: int,
) -> RecipePhase | None:
    """Fetch the *current* recipe phase payload for an active grow cycle.

    Used when ``config_mode=live`` — hot-reload picks up inline edits made
    via `PUT /api/grow-cycles/{id}/phase-config` to the active phase.
    """
    row = await conn.fetchrow(
        """
        SELECT rp.config, rp.id
        FROM grow_cycles gc
        JOIN recipe_phases rp ON rp.id = gc.current_phase_id
        WHERE gc.id = $1
        """,
        grow_cycle_id,
    )
    if row is None or not isinstance(row.get("config"), Mapping):
        return None
    try:
        return load_recipe_phase(row["config"], zone_id=zone_id)
    except (ConfigValidationError, ConfigLoaderError) as exc:
        _logger.warning(
            "live_reload: recipe_phase validation failed zone_id=%s phase_id=%s err=%s",
            zone_id, row.get("id"), exc,
        )
        return None
