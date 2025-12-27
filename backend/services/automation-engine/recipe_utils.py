"""
Utility functions for working with recipes and phases.
DEPRECATED: Эти функции используют legacy таблицы. Используйте LaravelApiRepository или GrowCycleRepository вместо них.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from common.utils.time import utcnow
from common.db import fetch, execute

logger = logging.getLogger(__name__)


async def get_recipe_by_id(recipe_id: int) -> Optional[Dict[str, Any]]:
    """Fetch recipe by ID."""
    rows = await fetch(
        """
        SELECT id, name, description, created_at
        FROM recipes
        WHERE id = $1
        """,
        recipe_id,
    )
    if rows and len(rows) > 0:
        return rows[0]
    return None


async def get_recipe_phases(recipe_id: int) -> List[Dict[str, Any]]:
    """
    DEPRECATED: Используйте recipe_revisions и recipe_revision_phases вместо recipe_phases.
    Fetch all phases for a recipe, ordered by phase_index (legacy).
    """
    logger.warning('get_recipe_phases() is deprecated - use recipe_revisions instead')
    # LEGACY FUNCTION DISABLED - tables removed
    return []
    # Пытаемся получить из новой модели
    try:
        revision_rows = await fetch(
            """
            SELECT id
            FROM recipe_revisions
            WHERE recipe_id = $1 AND status = 'PUBLISHED'
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            recipe_id,
        )
        if revision_rows:
            revision_id = revision_rows[0]["id"]
            phase_rows = await fetch(
                """
                SELECT phase_index, name, duration_hours, duration_days,
                       ph_target, ec_target, temp_air_target, humidity_target
                FROM recipe_revision_phases
                WHERE recipe_revision_id = $1
                ORDER BY phase_index ASC
                """,
                revision_id,
            )
            # Преобразуем в старый формат для совместимости
            result = []
            for row in phase_rows:
                targets = {}
                if row.get("ph_target") is not None:
                    targets["ph"] = row["ph_target"]
                if row.get("ec_target") is not None:
                    targets["ec"] = row["ec_target"]
                if row.get("temp_air_target") is not None:
                    targets["temp_air"] = row["temp_air_target"]
                if row.get("humidity_target") is not None:
                    targets["humidity_air"] = row["humidity_target"]
                
                duration_hours = row.get("duration_hours")
                if not duration_hours and row.get("duration_days"):
                    duration_hours = row["duration_days"] * 24
                
                result.append({
                    "id": None,  # В новой модели нет id в старом смысле
                    "recipe_id": recipe_id,
                    "phase_index": row["phase_index"],
                    "name": row["name"],
                    "duration_hours": duration_hours or 0,
                    "targets": targets,
                    "created_at": None,
                })
            return result
    except Exception as e:
        logger.warning(f'Failed to get phases from new model, falling back to legacy: {e}')
    
    # Fallback на legacy таблицу (если еще существует)
    rows = await fetch(
        """
        SELECT id, recipe_id, phase_index, name, duration_hours, targets, created_at
        FROM recipe_phases
        WHERE recipe_id = $1
        ORDER BY phase_index ASC
        """,
        recipe_id,
    )
    return rows


async def get_zone_recipe_instance(zone_id: int) -> Optional[Dict[str, Any]]:
    """
    DEPRECATED: Используйте GrowCycleRepository.get_active_cycle_for_zone() вместо этого.
    Fetch active recipe instance for zone (legacy).
    """
    logger.warning('get_zone_recipe_instance() is deprecated - use GrowCycleRepository instead')
    # LEGACY FUNCTION DISABLED - tables removed
    return None
    # Пытаемся получить из новой модели
    try:
        from repositories.grow_cycle_repository import GrowCycleRepository
        grow_cycle_repo = GrowCycleRepository()
        cycle = await grow_cycle_repo.get_active_cycle_for_zone(zone_id)
        if cycle:
            # Преобразуем в старый формат для совместимости
            return {
                "id": cycle.get("id"),
                "zone_id": zone_id,
                "recipe_id": cycle.get("recipe_id"),
                "current_phase_index": cycle.get("current_phase_id"),  # Приблизительно
                "started_at": cycle.get("started_at"),
                "updated_at": cycle.get("updated_at"),
            }
    except Exception as e:
        logger.warning(f'Failed to get cycle from new model, falling back to legacy: {e}')
    
    # Fallback на legacy таблицу (если еще существует)
    rows = await fetch(
        """
        SELECT id, zone_id, recipe_id, current_phase_index, started_at, updated_at
        FROM zone_recipe_instances
        WHERE zone_id = $1
        """,
        zone_id,
    )
    if rows and len(rows) > 0:
        return rows[0]
    return None


async def calculate_current_phase(zone_id: int) -> Optional[Dict[str, Any]]:
    """
    Calculate current phase for zone based on time elapsed.
    Returns None if no recipe instance exists, or dict with:
    - phase_index: calculated phase index
    - phase_info: phase details
    - time_in_phase_hours: hours elapsed in current phase
    - phase_progress: 0.0-1.0 progress in current phase
    - should_transition: bool indicating if phase should change
    """
    # LEGACY FUNCTION DISABLED - tables removed
    return None
    instance = await get_zone_recipe_instance(zone_id)
    if not instance:
        return None

    recipe_id = instance["recipe_id"]
    started_at = instance["started_at"]
    current_phase_index = instance["current_phase_index"]

    # Get all phases
    phases = await get_recipe_phases(recipe_id)
    if not phases:
        return None

    # Sort phases by phase_index
    phases_sorted = sorted(phases, key=lambda p: p["phase_index"])

    # Calculate total elapsed time
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    elif not isinstance(started_at, datetime):
        return None

    # База хранит timestamps без таймзоны, приводим их к UTC
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    now = datetime.now(started_at.tzinfo) if started_at.tzinfo else utcnow()

    elapsed_hours = (now - started_at).total_seconds() / 3600

    # Calculate which phase we should be in
    cumulative_hours = 0.0
    target_phase_index = 0

    for phase in phases_sorted:
        duration = phase["duration_hours"]
        if elapsed_hours < cumulative_hours + duration:
            target_phase_index = phase["phase_index"]
            break
        cumulative_hours += duration
    else:
        # All phases completed - stay on last phase
        target_phase_index = phases_sorted[-1]["phase_index"]

    # Get current phase info
    current_phase = None
    for phase in phases_sorted:
        if phase["phase_index"] == current_phase_index:
            current_phase = phase
            break

    if not current_phase:
        return None

    # Calculate time in current phase
    # First, calculate cumulative hours up to current phase
    phase_start_cumulative = 0.0
    for phase in phases_sorted:
        if phase["phase_index"] < current_phase_index:
            phase_start_cumulative += phase["duration_hours"]
        else:
            break

    time_in_phase_hours = elapsed_hours - phase_start_cumulative
    phase_duration = current_phase["duration_hours"]
    phase_progress = min(1.0, max(0.0, time_in_phase_hours / phase_duration)) if phase_duration > 0 else 0.0

    # Check if we should transition to next phase
    should_transition = target_phase_index > current_phase_index

    return {
        "phase_index": current_phase_index,
        "target_phase_index": target_phase_index,
        "phase_info": current_phase,
        "time_in_phase_hours": time_in_phase_hours,
        "phase_progress": phase_progress,
        "should_transition": should_transition,
    }


async def get_phase_targets(zone_id: int) -> Optional[Dict[str, Any]]:
    """Get targets for current phase of zone's recipe."""
    instance = await get_zone_recipe_instance(zone_id)
    if not instance:
        return None

    recipe_id = instance["recipe_id"]
    phase_index = instance["current_phase_index"]

    rows = await fetch(
        """
        SELECT targets, name as phase_name, duration_hours
        FROM recipe_phases
        WHERE recipe_id = $1 AND phase_index = $2
        """,
        recipe_id,
        phase_index,
    )

    if rows and len(rows) > 0:
        return {
            "targets": rows[0]["targets"],
            "phase_name": rows[0]["phase_name"],
            "duration_hours": rows[0]["duration_hours"],
        }
    return None


async def advance_phase(zone_id: int, new_phase_index: int) -> bool:
    """
    Advance zone recipe to new phase.
    Returns True if successful, False otherwise.
    """
    try:
        await execute(
            """
            UPDATE zone_recipe_instances
            SET current_phase_index = $1, updated_at = NOW()
            WHERE zone_id = $2
            """,
            new_phase_index,
            zone_id,
        )
        return True
    except Exception:
        return False
