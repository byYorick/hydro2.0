"""Parse AI agent task definitions from Markdown into AIAgentTask."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .task_schema import AIAgentTask


SECTION_ALIASES: Dict[str, str] = {
    "название": "title",
    "название задачи": "title",
    "title": "title",
    "контекст": "context",
    "context": "context",
    "цель": "goal",
    "goal": "goal",
    "входные данные": "inputs",
    "inputs": "inputs",
    "ожидаемый результат": "expected",
    "expected result": "expected",
    "expected": "expected",
    "ограничения": "constraints",
    "constraints": "constraints",
    "формат ответа": "format",
    "format": "format",
    "заметки": "notes",
    "notes": "notes",
}


def parse_markdown(path: Path) -> AIAgentTask:
    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)

    data: Dict[str, Optional[str]] = {
        "title": None,
        "context": None,
        "goal": None,
        "notes": None,
    }
    lists: Dict[str, List[str]] = {
        "inputs": [],
        "expected": [],
        "constraints": [],
        "format": [],
    }

    for name, content in sections.items():
        key = SECTION_ALIASES.get(name.lower())
        if not key:
            continue

        if key in lists:
            lists[key] = _to_list(content)
        elif key in data:
            data[key] = content.strip()

    # Fallback: если нет явного title, возьмем первый заголовок файла
    if not data["title"]:
        first_heading = next(iter(sections.keys()), "").strip()
        if first_heading:
            data["title"] = first_heading

    task = AIAgentTask(
        title=data["title"] or "",
        context=data["context"] or "",
        goal=data["goal"] or "",
        inputs=lists["inputs"],
        expected=lists["expected"],
        constraints=lists["constraints"],
        format=lists["format"],
        notes=data["notes"],
    )
    task.validate()
    return task


def _split_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    buffer: List[str] = []
    heading_re = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")

    for line in text.splitlines():
        match = heading_re.match(line)
        if match:
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = match.group(1)
            buffer = []
        else:
            buffer.append(line)

    if current:
        sections[current] = "\n".join(buffer).strip()

    return sections


def _to_list(content: str) -> List[str]:
    items: List[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            stripped = stripped[1:].strip()
        if stripped:
            items.append(stripped)
    return items


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Parse AI agent task from Markdown.")
    parser.add_argument("path", type=Path, help="Path to markdown file with task description")
    parser.add_argument("--json", action="store_true", help="Print JSON representation")
    args = parser.parse_args(argv)

    try:
        task = parse_markdown(args.path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to parse task: {exc}", file=sys.stderr)
        return 1

    print(task.summary())
    if args.json:
        print(json.dumps(task.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
