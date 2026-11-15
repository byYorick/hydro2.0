"""Build/export the production image set for review, without pushing or deploying.

--plan needs only Git/Python. Real builds require a Docker-capable CI runner.
The manifest binds image IDs to the actual working tree, including new sources.
Frontend values are explicitly for qualification, never production credentials.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDS = (
    ("laravel", "backend/laravel", "Dockerfile.prod"),
    ("history-logger", "backend/services", "history-logger/Dockerfile"),
    ("automation-engine", "backend/services", "automation-engine/Dockerfile"),
    ("mqtt-bridge", "backend/services", "mqtt-bridge/Dockerfile"),
    ("telemetry-aggregator", "backend/services", "telemetry-aggregator/Dockerfile"),
)
INFRA = {
    "mqtt": "eclipse-mosquitto:2.0.22",
    "db": "timescale/timescaledb:2.28.2-pg16",
    "redis": "redis:7.4.9-alpine",
}


def source_identity() -> dict:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "backend/laravel",
            "backend/services",
            "schemas",
        ],
        cwd=ROOT,
    ).split(b"\0")
    digest = hashlib.sha256()
    for raw in sorted(set(paths)):
        if not raw:
            continue
        path = ROOT / raw.decode("utf-8", errors="surrogateescape")
        if not path.is_file() or path.is_symlink():
            continue
        # Runtime secrets are not source and are excluded from the manifest.
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        digest.update(raw + b"\0")
        with path.open("rb") as stream:
            digest.update(hashlib.file_digest(stream, "sha256").digest())
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    return {"commit": commit, "working_tree_sha256": digest.hexdigest(), "dirty": dirty}


def image_metadata(ref: str) -> dict:
    data = json.loads(
        subprocess.check_output(["docker", "image", "inspect", ref], text=True)
    )[0]
    return {key: data.get(key) for key in ("Id", "RepoDigests", "Architecture", "Os")}


def qualify(args: argparse.Namespace) -> int:
    identity = source_identity()
    tag = (
        args.tag
        or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        + "-"
        + identity["working_tree_sha256"][:12]
    )
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,127}", tag):
        raise ValueError("Invalid local qualification tag")
    builds = [
        {
            "service": name,
            "context": context,
            "dockerfile": dockerfile,
            "image": f"hydro-qualified/{name}:{tag}",
        }
        for name, context, dockerfile in BUILDS
    ]
    manifest = {
        "format_version": 1,
        "qualification_only": True,
        "source": identity,
        "frontend_host": "qualification.invalid",
        "builds": builds,
        "infra": INFRA,
        "status": "planned",
        "results": [],
        "pushed": False,
        "deployed": False,
    }
    for row in builds:
        if not (ROOT / row["context"] / row["dockerfile"]).is_file():
            raise ValueError("Missing production Dockerfile")
    if args.plan:
        print(json.dumps(manifest, indent=2))
        return 0
    if args.output is None:
        raise ValueError("--output is required for a real build")
    output = args.output.absolute()
    if any(output.is_relative_to(ROOT / folder) for folder in ("backend", "schemas")):
        raise ValueError(
            "Build logs and archives must be outside application build contexts"
        )
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest_path = output / "manifest.json"

    def save() -> None:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    def execute(name: str, command: list[str]) -> None:
        with (output / (name + ".log")).open("w") as log:
            subprocess.run(
                command, cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT
            )

    save()
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for row in builds:
            # Preserve any previously built candidate; use a fresh tag for a new run.
            exists = subprocess.run(
                ["docker", "image", "inspect", row["image"]],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if exists.returncode == 0:
                raise ValueError("Candidate tag already exists; choose another tag")
            command = [
                "docker",
                "build",
                "--pull",
                "--tag",
                row["image"],
                "--label",
                "org.opencontainers.image.revision=" + identity["commit"],
                "--label",
                "hydro.source-sha256=" + identity["working_tree_sha256"],
                "--file",
                str(ROOT / row["context"] / row["dockerfile"]),
            ]
            if row["service"] == "laravel":
                for key, value in {
                    "VITE_REVERB_HOST": "qualification.invalid",
                    "VITE_WS_HOST": "qualification.invalid",
                    "VITE_REVERB_PORT": "443",
                    "VITE_WS_PORT": "443",
                    "VITE_WS_TLS": "true",
                    "VITE_REVERB_SCHEME": "https",
                    "VITE_REVERB_APP_KEY": "qualification-public-key",
                    "VITE_PUSHER_APP_KEY": "qualification-public-key",
                }.items():
                    command += ["--build-arg", key + "=" + value]
            else:
                command += ["--build-arg", "INSTALL_DEV_DEPS=false"]
            command.append(str(ROOT / row["context"]))
            execute(row["service"], command)
            manifest["results"].append(
                {
                    "service": row["service"],
                    "image": row["image"],
                    **image_metadata(row["image"]),
                }
            )
            save()
        for name, ref in INFRA.items():
            execute(name, ["docker", "pull", ref])
            manifest["results"].append(
                {"service": name, "image": ref, **image_metadata(ref)}
            )
            save()
        if args.export_images:
            refs = [row["image"] for row in manifest["results"]]
            archive = output / "images.tar.gz"
            process = subprocess.Popen(
                ["docker", "image", "save", *refs], stdout=subprocess.PIPE
            )
            try:
                with gzip.open(archive, "wb", compresslevel=1) as target:
                    shutil.copyfileobj(process.stdout, target)
                if process.wait() != 0:
                    raise RuntimeError("Image export failed")
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
            with archive.open("rb") as stream:
                manifest["archive"] = {
                    "name": archive.name,
                    "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                }
        if source_identity()["working_tree_sha256"] != identity["working_tree_sha256"]:
            raise ValueError("Source files changed while images were building")
        manifest["status"] = "built"
        save()
        print(
            "Qualification images built; manifest written. No push or deployment performed."
        )
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        manifest["status"] = "failed"
        manifest["error_type"] = type(error).__name__
        save()
        print(
            "Image qualification failed; inspect the private build logs and manifest.",
            file=sys.stderr,
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--export-images", action="store_true")
    args = parser.parse_args()
    try:
        return qualify(args)
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            "Invalid qualification input or unavailable source checkout.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
