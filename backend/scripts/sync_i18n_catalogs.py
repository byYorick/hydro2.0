#!/usr/bin/env python3
"""Синхронизация канонических каталогов error_codes.json и alert_codes.json.

Source of truth:
  - backend/error_codes.json (включает слияние из node_error_codes.json)
  - backend/node_error_codes.json (фаза 5: прошивки / MQTT command_response)
  - backend/alert_codes.json

Копии:
  - backend/laravel/error_codes.json
  - backend/laravel/resources/js/constants/error_codes.json
  - backend/laravel/alert_codes.json

Запуск из корня репозитория:
  python3 backend/scripts/sync_i18n_catalogs.py
  python3 backend/scripts/sync_i18n_catalogs.py --check   # exit 1 при рассинхроне
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

NODE_ERROR_CANONICAL = BACKEND / "node_error_codes.json"
ERROR_CANONICAL = BACKEND / "error_codes.json"
ANDROID_I18N = ROOT / "mobile" / "app" / "android" / "app" / "src" / "main" / "assets" / "i18n"

ERROR_COPIES = [
    BACKEND / "laravel" / "error_codes.json",
    BACKEND / "laravel" / "resources" / "js" / "constants" / "error_codes.json",
    ANDROID_I18N / "error_codes.json",
]

ALERT_CANONICAL = BACKEND / "alert_codes.json"
ALERT_COPIES = [
    BACKEND / "laravel" / "alert_codes.json",
    ANDROID_I18N / "alert_codes.json",
]

RAW_TRANSLATION_CANONICAL = BACKEND / "api_error_raw_translations.json"
RAW_TRANSLATION_COPIES = [
    BACKEND / "laravel" / "api_error_raw_translations.json",
    BACKEND / "services" / "api_error_raw_translations.json",
    BACKEND / "services" / "common" / "api_error_raw_translations.json",
]


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def sync_file(canonical: Path, copies: list[Path], *, check_only: bool) -> bool:
    if not canonical.is_file():
        print(f"ERROR: missing canonical file {canonical}", file=sys.stderr)
        return False

    canonical_text = canonical.read_text(encoding="utf-8")
    ok = True
    for copy_path in copies:
        if not check_only:
            copy_path.parent.mkdir(parents=True, exist_ok=True)
        elif not copy_path.parent.exists():
            print(f"WARN: skip missing directory for {copy_path}", file=sys.stderr)
            continue
        if check_only:
            if not copy_path.is_file() or copy_path.read_text(encoding="utf-8") != canonical_text:
                print(f"OUT OF SYNC: {copy_path.relative_to(ROOT)}", file=sys.stderr)
                ok = False
        else:
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical, copy_path)
            print(f"Synced {copy_path.relative_to(ROOT)}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only verify copies match canonical (exit 1 on drift)",
    )
    parser.add_argument(
        "--skip-node-build",
        action="store_true",
        help="не запускать build_node_error_catalog.py перед sync",
    )
    args = parser.parse_args()

    if not args.check and not args.skip_node_build:
        import subprocess

        build_script = BACKEND / "scripts" / "build_node_error_catalog.py"
        if build_script.is_file():
            subprocess.run([sys.executable, str(build_script)], check=True, cwd=str(ROOT))

    ok = True
    ok = sync_file(ERROR_CANONICAL, ERROR_COPIES, check_only=args.check) and ok
    ok = sync_file(ALERT_CANONICAL, ALERT_COPIES, check_only=args.check) and ok
    if RAW_TRANSLATION_CANONICAL.is_file():
        ok = sync_file(RAW_TRANSLATION_CANONICAL, RAW_TRANSLATION_COPIES, check_only=args.check) and ok

    if args.check and not ok:
        return 1
    if not args.check:
        print("Catalog sync complete.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
