"""Load E2E YAML scenarios and expand named step sequences.

Helper fragments (kind: step_sequences) live next to scenarios, e.g.
``scenarios/ae3lite/_two_tank_fill_helper.yaml``. A scenario splices a
sequence with:

    - include_sequence: two_tank_fill_ca

Optional keys on the include item:
    helper: _two_tank_fill_helper.yaml   # default, relative to the scenario file
    aliases: {old_step_name: new_step_name}  # keep contract step names
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

INCLUDE_KEY = "include_sequence"
DEFAULT_HELPER_NAME = "_two_tank_fill_helper.yaml"
LIST_SECTIONS = ("actions", "cleanup", "assertions", "steps")


def load_scenario_file(path: Path | str) -> dict[str, Any]:
    """Load a scenario YAML and expand ``include_sequence`` directives."""
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Scenario root must be a mapping: {scenario_path}")
    return expand_include_sequences(payload, scenario_path.parent)


def expand_include_sequences(
    scenario: dict[str, Any],
    base_dir: Path,
) -> dict[str, Any]:
    """Return a copy of *scenario* with include_sequence items spliced in."""
    expanded = copy.deepcopy(scenario)
    for section in LIST_SECTIONS:
        items = expanded.get(section)
        if isinstance(items, list):
            expanded[section] = _expand_step_list(items, base_dir)
    return expanded


def _expand_step_list(items: list[Any], base_dir: Path) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict) and INCLUDE_KEY in item:
            out.extend(_load_sequence_steps(item, base_dir))
        else:
            out.append(item)
    return out


def _load_sequence_steps(include_item: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    seq_name = str(include_item.get(INCLUDE_KEY) or "").strip()
    if not seq_name:
        raise ValueError("include_sequence requires a non-empty sequence name")

    helper_name = str(include_item.get("helper") or DEFAULT_HELPER_NAME)
    helper_path = Path(helper_name)
    if not helper_path.is_absolute():
        helper_path = (base_dir / helper_path).resolve()
    if not helper_path.is_file():
        raise FileNotFoundError(f"Step-sequence helper not found: {helper_path}")

    with helper_path.open("r", encoding="utf-8") as handle:
        helper = yaml.safe_load(handle) or {}
    if not isinstance(helper, dict):
        raise ValueError(f"Helper root must be a mapping: {helper_path}")

    sequences = helper.get("sequences") or {}
    if not isinstance(sequences, dict) or seq_name not in sequences:
        known = sorted(str(key) for key in sequences)
        raise KeyError(
            f"Sequence '{seq_name}' is missing in {helper_path.name}; known={known}"
        )

    raw_steps = sequences[seq_name]
    if not isinstance(raw_steps, list):
        raise ValueError(f"Sequence '{seq_name}' must be a list of steps")

    aliases = include_item.get("aliases") or {}
    if aliases and not isinstance(aliases, dict):
        raise ValueError("include_sequence.aliases must be a mapping")

    steps = [copy.deepcopy(step) for step in raw_steps if isinstance(step, dict)]
    if aliases:
        steps = [_apply_step_aliases(step, aliases) for step in steps]
    return steps


def _apply_step_aliases(step: dict[str, Any], aliases: dict[str, Any]) -> dict[str, Any]:
    renamed = copy.deepcopy(step)
    original_name = str(renamed.get("step") or "")
    alias = aliases.get(original_name)
    if isinstance(alias, str) and alias.strip() and alias != original_name:
        renamed["step"] = alias
    return _rewrite_alias_refs(renamed, aliases)


def _rewrite_alias_refs(value: Any, aliases: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_alias_refs(item, aliases) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_alias_refs(item, aliases) for item in value]
    if not isinstance(value, str):
        return value
    rewritten = value
    for old, new in aliases.items():
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        if not old or not new or old == new:
            continue
        rewritten = rewritten.replace(f"${{{old}_response", f"${{{new}_response")
        if rewritten == f"{old}_response":
            rewritten = f"{new}_response"
    return rewritten
