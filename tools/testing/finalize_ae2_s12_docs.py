#!/usr/bin/env python3
"""Finalize AE2 S12 docs after strict staging gate pass."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise ValueError(f"pattern not found for {label}: {old!r}")
    return text.replace(old, new, 1)


def _replace_required_or_already(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise ValueError(f"pattern not found for {label}: {old!r} or {new!r}")


def _update_current_state(content: str, today: str) -> str:
    updated = content
    updated, replaced = re.subn(
        r"\*\*Дата обновления:\*\* [0-9]{4}-[0-9]{2}-[0-9]{2}",
        f"**Дата обновления:** {today}",
        updated,
        count=1,
    )
    if replaced != 1:
        raise ValueError("failed to update AE2_CURRENT_STATE date")
    updated = _replace_required_or_already(
        updated,
        "- `S12` Acceptance: IN_PROGRESS.",
        "- `S12` Acceptance: COMPLETED.",
        "AE2_CURRENT_STATE current stage",
    )

    completed_stage_line = "- `S12` Load + Chaos + Acceptance: COMPLETED."
    if completed_stage_line not in updated:
        marker = "- `S11` Observability + Integration + Cutover: COMPLETED.\n"
        if marker not in updated:
            raise ValueError("marker for completed stage insertion not found")
        updated = updated.replace(marker, marker + completed_stage_line + "\n", 1)

    # Append final increment if not yet present.
    if not re.search(r"S12 \(increment \d+\): финальный стендовый gate закрыт", updated):
        s12_numbers = [int(x) for x in re.findall(r"S12 \(increment (\d+)\):", updated)]
        next_s12_increment = (max(s12_numbers) + 1) if s12_numbers else 1

        section_match = re.search(r"## 4\. Зафиксированные решения\n(.+?)\n## 5\. Известные риски", updated, flags=re.S)
        if not section_match:
            raise ValueError("section ## 4 not found in AE2_CURRENT_STATE")
        section_body = section_match.group(1)
        absolute_numbers = [int(x) for x in re.findall(r"^(\d+)\.", section_body, flags=re.M)]
        next_absolute = (max(absolute_numbers) + 1) if absolute_numbers else 1

        final_line = (
            f"{next_absolute}. S12 (increment {next_s12_increment}): финальный стендовый gate закрыт "
            f"(strict metadata remote check PASS), `S12` переведен в `COMPLETED`."
        )
        insertion_point = "\n## 5. Известные риски"
        updated = updated.replace(insertion_point, f"\n{final_line}{insertion_point}", 1)

    return updated


def _run_strict_gate(repo_root: Path) -> None:
    checker = repo_root / "tools/testing/check_ae2_s12_release_bundle.sh"
    env = dict(os.environ)
    env["AE2_S12_REQUIRE_REMOTE_METADATA"] = "true"
    env["AE2_S12_EXPECT_DECISION"] = "ALLOW_FULL_ROLLOUT"
    subprocess.run([str(checker)], cwd=str(repo_root), env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes in place.")
    parser.add_argument("--skip-gate-check", action="store_true", help="Skip strict staging gate check.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    task_path = repo_root / "doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S12_TASK.md"
    acceptance_path = repo_root / "doc_ai/10_AI_DEV_GUIDES/AE2_ACCEPTANCE_VALIDATION_S12.md"
    final_report_path = repo_root / "doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S12_FINAL_REPORT.md"
    current_state_path = repo_root / "doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md"

    task = _read(task_path)
    acceptance = _read(acceptance_path)
    final_report = _read(final_report_path)
    current_state = _read(current_state_path)

    today = dt.date.today().isoformat()

    updated_task = _replace_required_or_already(
        task,
        "**Статус:** IN_PROGRESS",
        "**Статус:** COMPLETED",
        "AE2_STAGE_S12_TASK status",
    )
    updated_acceptance = _replace_required_or_already(
        acceptance,
        "**Статус:** IN_PROGRESS",
        "**Статус:** COMPLETED",
        "AE2_ACCEPTANCE_VALIDATION_S12 status",
    )
    updated_final_report = _replace_required_or_already(
        final_report,
        "**Статус:** DRAFT (staging gate pending)",
        "**Статус:** COMPLETED",
        "AE2_STAGE_S12_FINAL_REPORT status",
    )
    updated_current_state = _update_current_state(current_state, today=today)

    changed = []
    if updated_task != task:
        changed.append(str(task_path.relative_to(repo_root)))
    if updated_acceptance != acceptance:
        changed.append(str(acceptance_path.relative_to(repo_root)))
    if updated_final_report != final_report:
        changed.append(str(final_report_path.relative_to(repo_root)))
    if updated_current_state != current_state:
        changed.append(str(current_state_path.relative_to(repo_root)))

    if not changed:
        print("no_changes_needed=true")
        return 0

    if not args.apply:
        print("dry_run=true")
        print("would_change_files:")
        for item in changed:
            print(f"- {item}")
        return 0

    if args.skip_gate_check:
        unsafe_finalize = str(os.getenv("AE2_S12_ALLOW_UNSAFE_FINALIZE", "")).strip().lower()
        if unsafe_finalize not in {"1", "true", "yes"}:
            print("unsafe_finalize_guard=false")
            print("reason=--skip-gate-check requires AE2_S12_ALLOW_UNSAFE_FINALIZE=true")
            return 2
        print("unsafe_finalize_guard=true")
        print("warning=strict gate check is skipped by explicit override")
    else:
        try:
            _run_strict_gate(repo_root)
        except subprocess.CalledProcessError as exc:
            print("strict_gate_passed=false")
            print(f"strict_gate_exit_code={exc.returncode}")
            return exc.returncode

    _write(task_path, updated_task)
    _write(acceptance_path, updated_acceptance)
    _write(final_report_path, updated_final_report)
    _write(current_state_path, updated_current_state)

    print("applied=true")
    print("changed_files:")
    for item in changed:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
