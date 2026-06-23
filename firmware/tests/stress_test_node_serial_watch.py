#!/usr/bin/env python3
"""Фоновый UART-монитор test_node: ловит reboot/panic/abort во время стресс-теста."""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pip install pyserial") from exc

CRASH_PATTERNS = [
    re.compile(r"Guru Meditation", re.I),
    re.compile(r"abort\(\) was called", re.I),
    re.compile(r"ESP_ERROR_CHECK failed", re.I),
    re.compile(r"Stack overflow", re.I),
    re.compile(r"Task watchdog", re.I),
    re.compile(r"Brownout detector", re.I),
    re.compile(r"panic_abort", re.I),
    re.compile(r"CORRUPT HEAP", re.I),
]

REBOOT_PATTERNS = [
    re.compile(r"^rst:0x", re.I),
]

BOOT_PATTERNS = [
    re.compile(r"Test node starting", re.I),
    re.compile(r"Test node started successfully", re.I),
]


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    parser = argparse.ArgumentParser(description="UART watch for test_node crashes")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=int, default=180, help="Секунд мониторинга")
    parser.add_argument("--grace-sec", type=int, default=12, help="Игнорировать reboot в начале")
    parser.add_argument("--log-file", default="/tmp/test_node_stress_serial.log")
    parser.add_argument("--reset-on-start", action="store_true", default=False)
    args = parser.parse_args()

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    crashes: list[str] = []
    reboots_after_grace = 0
    boots = 0
    started_ok = 0

    with serial.Serial(args.port, args.baud, timeout=0.2) as ser, log_path.open("a", encoding="utf-8") as logf:
        if args.reset_on_start:
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.rts = False
            time.sleep(0.1)
            ser.dtr = True
            time.sleep(0.05)
            ser.dtr = False

        print(f"[{ts()}] serial watch on {args.port}, duration={args.duration}s, log={log_path}")
        logf.write(f"\n===== stress watch start {datetime.now().isoformat()} =====\n")
        logf.flush()

        deadline = time.time() + args.duration
        grace_until = time.time() + args.grace_sec
        while time.time() < deadline:
            chunk = ser.read(4096)
            if not chunk:
                continue
            text = chunk.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            logf.write(text)
            logf.flush()

            for line in text.splitlines():
                now = time.time()
                for pat in BOOT_PATTERNS:
                    if pat.search(line):
                        if "starting" in line.lower():
                            boots += 1
                            if now >= grace_until:
                                reboots_after_grace += 1
                                entry = f"{ts()} unexpected boot: {line.strip()}"
                                crashes.append(entry)
                                print(f"\n[{ts()}] *** REBOOT: {line.strip()} ***\n", flush=True)
                        if "started successfully" in line.lower():
                            started_ok += 1
                for pat in CRASH_PATTERNS:
                    if pat.search(line):
                        entry = f"{ts()} {line.strip()}"
                        crashes.append(entry)
                        print(f"\n[{ts()}] *** CRASH SIGNAL: {line.strip()} ***\n", flush=True)
                if now >= grace_until:
                    for pat in REBOOT_PATTERNS:
                        if pat.search(line):
                            reboots_after_grace += 1
                            entry = f"{ts()} reboot marker: {line.strip()}"
                            crashes.append(entry)
                            print(f"\n[{ts()}] *** REBOOT: {line.strip()} ***\n", flush=True)

    print(
        f"\n[{ts()}] serial watch done: boots={boots} started_ok={started_ok} "
        f"reboots_after_grace={reboots_after_grace} crash_signals={len(crashes)}"
    )
    if crashes:
        print("--- crash lines ---")
        for item in crashes[-20:]:
            print(item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
