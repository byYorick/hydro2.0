"""Minimal schema and validator for AI agent tasks."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence


@dataclass
class AIAgentTask:
    title: str
    context: str
    goal: str
    inputs: List[str] = field(default_factory=list)
    expected: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    format: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    def validate(self) -> None:
        """Validate required fields and basic content rules."""
        missing: List[str] = []
        if not self.title.strip():
            missing.append("title")
        if not self.context.strip():
            missing.append("context")
        if not self.goal.strip():
            missing.append("goal")

        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        for field_name, items in [
            ("inputs", self.inputs),
            ("expected", self.expected),
            ("constraints", self.constraints),
            ("format", self.format),
        ]:
            _validate_list(field_name, items)

    def summary(self) -> str:
        """Return one-line summary for CLI usage."""
        return f"{self.title} :: goal={self.goal} :: expected={len(self.expected)} items"


def _validate_list(name: str, values: Sequence[str]) -> None:
    for idx, value in enumerate(values):
        if not isinstance(value, str):
            raise ValueError(f"{name}[{idx}] must be string, got {type(value).__name__}")
        if not value.strip():
            raise ValueError(f"{name}[{idx}] must not be empty")


def load_task(path: Path) -> AIAgentTask:
    """Load task definition from JSON file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    task = AIAgentTask(
        title=raw.get("title", "").strip(),
        context=raw.get("context", "").strip(),
        goal=raw.get("goal", "").strip(),
        inputs=list(raw.get("inputs", []) or []),
        expected=list(raw.get("expected", []) or []),
        constraints=list(raw.get("constraints", []) or []),
        format=list(raw.get("format", []) or []),
        notes=(raw.get("notes") or None),
    )
    task.validate()
    return task


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m tools.ai_agents.task_schema <task.json>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Task file not found: {path}", file=sys.stderr)
        return 1

    try:
        task = load_task(path)
    except Exception as exc:  # noqa: BLE001
        print(f"Invalid task: {exc}", file=sys.stderr)
        return 1

    print(task.summary())
    print("Context:", task.context)
    print("Inputs:", len(task.inputs))
    print("Expected artifacts:", len(task.expected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
