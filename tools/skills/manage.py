#!/usr/bin/env python3
"""Offline installation and structural validation of repository-owned skills."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools/skills/project-skills.json"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")


def inside(relative: str) -> Path:
    path = ROOT / relative
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"path escapes repository: {relative}")
    return path


def scalar(value: str) -> str:
    """Read the intentionally small YAML subset used by project frontmatter.

    Strings are plain one-line values or JSON-quoted strings (valid YAML).
    Unsupported YAML is rejected, rather than silently interpreted incorrectly.
    """
    if value.startswith('"'):
        result = json.loads(value)
        if not isinstance(result, str):
            raise ValueError("frontmatter value must be a string")
        return result
    if not value or ": " in value or value in {"|", ">", ">-", "|-"}:
        raise ValueError("use a one-line JSON-quoted string for this value")
    return value


def frontmatter(path: Path) -> tuple[dict[str, str], dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc
    fields: dict[str, str] = {}
    metadata: dict[str, str] = {}
    in_metadata = False
    for line in lines[1:end]:
        if line == "metadata:":
            if in_metadata:
                raise ValueError("duplicate metadata mapping")
            in_metadata = True
            continue
        match = re.fullmatch(r"(  )?([a-z][a-z0-9-]*): (.+)", line)
        if not match:
            raise ValueError(f"unsupported frontmatter line: {line}")
        nested, key, value = match.groups()
        if nested and not in_metadata:
            raise ValueError("metadata field outside metadata mapping")
        target = metadata if nested else fields
        if not nested:
            in_metadata = False
        if key in target:
            raise ValueError(f"duplicate field: {key}")
        target[key] = scalar(value)
    unknown = set(fields) - {"name", "description", "license", "compatibility"}
    if unknown:
        raise ValueError(f"custom fields belong in metadata: {sorted(unknown)}")
    return fields, metadata, "\n".join(lines[end + 1 :])


def check_links(path: Path, body: str) -> None:
    fence: str | None = None
    for number, line in enumerate(body.splitlines(), 1):
        marker = re.match(r"\s*(`{3,}|~{3,})", line)
        if marker:
            char = marker.group(1)[0]
            fence = char if fence is None else None if fence == char else fence
            continue
        if fence:
            continue
        for target in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)\)", line):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                raise ValueError(f"broken local link in body line {number}: {target}")


def validate(manifest: dict, *, aliases: bool) -> int:
    if manifest.get("version") != 1:
        raise ValueError("unsupported project-skills manifest version")
    sources: dict[str, dict] = {}
    for source in manifest["sources"]:
        source_id = source["id"]
        if source_id in sources:
            raise ValueError(f"duplicate source id: {source_id}")
        if not SHA.fullmatch(source["commit"]) or not SHA.fullmatch(source["blob_sha"]):
            raise ValueError(f"unpinned source: {source_id}")
        expected = f"https://github.com/{source['repository']}/blob/{source['commit']}/{source['path']}"
        if source["url"] != expected:
            raise ValueError(f"source URL does not match pinned commit: {source_id}")
        if not inside(source["license_file"]).is_file() or not source["adaptation"]:
            raise ValueError(f"missing license/adaptation: {source_id}")
        sources[source_id] = source

    names: set[str] = set()
    claimed_paths: set[Path] = set()
    count = 0
    for entry in manifest["skills"]:
        name = entry["name"]
        if not NAME.fullmatch(name) or len(name) > 64 or name in names:
            raise ValueError(f"invalid/duplicate name: {name}")
        names.add(name)
        directory = inside(entry["path"])
        if directory.name != name or directory.is_symlink():
            raise ValueError(f"canonical skill must be a real directory named {name}")
        if directory in claimed_paths:
            raise ValueError(f"duplicate canonical path: {directory}")
        claimed_paths.add(directory)
        fields, meta, body = frontmatter(directory / "SKILL.md")
        if fields.get("name") != name or not 1 <= len(fields.get("description", "")) <= 1024:
            raise ValueError(f"invalid name/description in {entry['path']}")
        if "compatibility" in fields and not 1 <= len(fields["compatibility"]) <= 500:
            raise ValueError(f"invalid compatibility in {name}")
        if meta.get("lifecycle") != "active" or meta.get("type") not in {"workflow", "domain", "meta"}:
            raise ValueError(f"invalid metadata in {name}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", meta.get("version", "")):
            raise ValueError(f"missing semantic metadata version in {name}")
        if not body.strip() or len(body.splitlines()) >= 500:
            raise ValueError(f"empty/oversized body in {name}")
        check_links(directory / "SKILL.md", body)
        if not (directory / "CHANGELOG.md").is_file():
            raise ValueError(f"missing changelog in {name}")
        evaluation = json.loads((directory / "evals/evals.json").read_text(encoding="utf-8"))
        if evaluation.get("skill_name") != name or not evaluation.get("evals"):
            raise ValueError(f"missing evaluation scenarios in {name}")
        ids: set[int] = set()
        for case in evaluation["evals"]:
            case_id = case["id"]
            if not isinstance(case_id, int) or case_id in ids:
                raise ValueError(f"invalid/duplicate evaluation id in {name}")
            ids.add(case_id)
            for key in ("prompt", "expected_output"):
                if not isinstance(case.get(key), str) or not case[key].strip():
                    raise ValueError(f"missing {key} in {name} evaluation {case_id}")
            expectations = case.get("expectations")
            if not isinstance(expectations, list) or not expectations or not all(isinstance(x, str) and x.strip() for x in expectations):
                raise ValueError(f"missing expectations in {name} evaluation {case_id}")
            if "should_trigger" in case and not isinstance(case["should_trigger"], bool):
                raise ValueError(f"invalid should_trigger in {name} evaluation {case_id}")
        for source_id in entry["sources"]:
            source = sources[source_id]
            if fields.get("license") != source["license"] or meta.get("upstream") != source_id:
                raise ValueError(f"source/license mismatch in {name}")
        for relative in entry["aliases"]:
            alias = inside(relative)
            if alias in claimed_paths or alias.name != name:
                raise ValueError(f"invalid/duplicate alias: {relative}")
            claimed_paths.add(alias)
            if aliases and (not alias.is_symlink() or alias.resolve() != directory.resolve()):
                raise ValueError(f"missing/incorrect alias: {relative}; run make skills-install")
        count += len(evaluation["evals"])
    return count


def install(manifest: dict) -> None:
    validate(manifest, aliases=False)
    for entry in manifest["skills"]:
        target = inside(entry["path"])
        for relative in entry["aliases"]:
            alias = inside(relative)
            if os.path.lexists(alias):
                if not alias.is_symlink() or alias.resolve() != target.resolve():
                    raise ValueError(f"refusing to overwrite existing path: {relative}")
                continue
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.symlink_to(os.path.relpath(target, alias.parent), target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check", "list"))
    command = parser.parse_args().command
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if command == "install":
            install(manifest)
        if command == "list":
            for entry in manifest["skills"]:
                print(f"{entry['name']}: {entry['path']}")
            return 0
        count = validate(manifest, aliases=True)
        print(f"OK: {len(manifest['skills'])} project skills, {count} evaluation scenarios, pinned sources, licenses and local aliases")
        print("Structural validation only; model evaluations and runtime checks were not executed.")
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
