"""
Utility functions for working with recipes and phases.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from common.db import fetch, execute


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
    """Fetch all phases for a recipe, ordered by phase_index."""
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
    """Fetch active recipe instance for zone."""
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
    elif isinstance(started_at, datetime):
        pass
    else:
        return None

    now = datetime.utcnow()
    if started_at.tzinfo:
        now = datetime.now(started_at.tzinfo)

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

