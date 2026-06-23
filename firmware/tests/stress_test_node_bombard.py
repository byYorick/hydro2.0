#!/usr/bin/env python3
"""
Стресс-тест test_node: параллельная MQTT-бомбардировка командами всем виртуальным нодам.

Пример:
  python3 firmware/tests/stress_test_node_bombard.py \\
    --mqtt-host localhost --mqtt-port 1883 \\
    --duration 120 --workers 6 --rate 30
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

DEFAULT_SECRET = os.getenv("NODE_DEFAULT_SECRET", "hydro-default-secret-key-2025")
DEFAULT_GH = "gh-test-1"
DEFAULT_ZONE = "zn-test-1"

# (node_uid, channel, cmd, params_factory)
SCENARIOS: List[Tuple[str, str, str, Callable[[], Dict]]] = [
    ("nd-test-irrig-1", "valve_clean_fill", "set_relay", lambda: {"state": random.choice([True, False])}),
    ("nd-test-irrig-1", "valve_solution_fill", "set_relay", lambda: {"state": random.choice([True, False])}),
    ("nd-test-irrig-1", "valve_irrigation", "set_relay", lambda: {"state": random.choice([True, False])}),
    ("nd-test-irrig-1", "pump_main", "set_relay", lambda: {"state": random.choice([True, False])}),
    (
        "nd-test-irrig-1",
        "pump_main",
        "run_pump",
        lambda: {"duration_ms": random.randint(80, 400)},
    ),
    ("nd-test-irrig-1", "storage_state", "state", lambda: {}),
    (
        "nd-test-irrig-1",
        "storage_state",
        "set_fault_mode",
        lambda: {
            "level_clean_min_override": random.choice([-1, 0, 1]),
            "level_clean_max_override": random.choice([-1, 0, 1]),
        },
    ),
    ("nd-test-ph-1", "pump_acid", "dose", lambda: {"ml": round(random.uniform(1.0, 8.0), 2)}),
    ("nd-test-ph-1", "pump_base", "dose", lambda: {"ml": round(random.uniform(1.0, 8.0), 2)}),
    ("nd-test-ph-1", "ph_sensor", "test_sensor", lambda: {}),
    ("nd-test-ph-1", "system", "activate_sensor_mode", lambda: {}),
    ("nd-test-ec-1", "pump_a", "dose", lambda: {"ml": round(random.uniform(1.0, 12.0), 2)}),
    ("nd-test-ec-1", "pump_b", "dose", lambda: {"ml": round(random.uniform(1.0, 12.0), 2)}),
    ("nd-test-ec-1", "ec_sensor", "test_sensor", lambda: {}),
    ("nd-test-ec-1", "system", "activate_sensor_mode", lambda: {}),
    ("nd-test-climate-1", "fan_air", "set_relay", lambda: {"state": random.choice([True, False])}),
    ("nd-test-climate-1", "heater", "set_pwm", lambda: {"duty": random.randint(0, 100)}),
    ("nd-test-light-1", "light_pwm", "set_pwm", lambda: {"duty": random.randint(0, 100)}),
    ("nd-test-soil-1", "system", "activate_sensor_mode", lambda: {}),
]


def build_signed_command(cmd_id: str, cmd: str, params: Dict) -> Dict:
    ts = int(time.time())
    base = {"cmd_id": cmd_id, "cmd": cmd, "params": params, "ts": ts}
    canonical = json.dumps(base, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(DEFAULT_SECRET.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    base["sig"] = sig
    return base


@dataclass
class Stats:
    sent: int = 0
    publish_fail: int = 0
    responses: int = 0
    terminal: int = 0
    ack_only: int = 0
    statuses: Counter = field(default_factory=Counter)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def inc_sent(self) -> None:
        with self.lock:
            self.sent += 1

    def inc_publish_fail(self) -> None:
        with self.lock:
            self.publish_fail += 1

    def add_response(self, status: str, is_terminal: bool) -> None:
        with self.lock:
            self.responses += 1
            self.statuses[status] += 1
            if is_terminal:
                self.terminal += 1
            elif status == "ACK":
                self.ack_only += 1


class StressBombard:
    def __init__(self, host: str, port: int, gh: str, zone: str):
        self.host = host
        self.port = port
        self.gh = gh
        self.zone = zone
        self.stats = Stats()
        self._stop = threading.Event()
        self._client: Optional[mqtt.Client] = None
        self._connected = threading.Event()

    def topic_command(self, node_uid: str, channel: str) -> str:
        return f"hydro/{self.gh}/{self.zone}/{node_uid}/{channel}/command"

    def topic_response_wildcard(self) -> str:
        return f"hydro/{self.gh}/{self.zone}/+/+/command_response"

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            client.subscribe(self.topic_response_wildcard(), qos=1)
        else:
            print(f"MQTT connect failed rc={rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        status = str(payload.get("status", "UNKNOWN"))
        is_terminal = status in {"DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT"}
        self.stats.add_response(status, is_terminal)

    def connect(self) -> None:
        self._client = mqtt.Client()
        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message
        self._client.connect(self.host, self.port, keepalive=60)
        self._client.loop_start()
        if not self._connected.wait(timeout=10):
            raise RuntimeError("MQTT connect timeout")

    def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def publish_one(self) -> None:
        assert self._client is not None
        node_uid, channel, cmd, params_factory = random.choice(SCENARIOS)
        cmd_id = f"stress-{uuid.uuid4().hex[:16]}"
        payload = build_signed_command(cmd_id, cmd, params_factory())
        topic = self.topic_command(node_uid, channel)
        raw = json.dumps(payload, separators=(",", ":"))
        rc = self._client.publish(topic, raw, qos=1)
        if rc.rc == mqtt.MQTT_ERR_SUCCESS:
            self.stats.inc_sent()
        else:
            self.stats.inc_publish_fail()

    def worker(self, rate_per_worker: float) -> None:
        interval = 1.0 / max(rate_per_worker, 0.1)
        while not self._stop.is_set():
            self.publish_one()
            time.sleep(interval)

    def run(self, duration: int, workers: int, rate: float) -> None:
        per_worker = rate / max(workers, 1)
        threads = [
            threading.Thread(target=self.worker, args=(per_worker,), daemon=True, name=f"stress-{i}")
            for i in range(workers)
        ]
        for t in threads:
            t.start()

        started = time.time()
        next_report = started + 5.0
        print(
            f"Stress started: duration={duration}s workers={workers} total_rate≈{rate}/s "
            f"gh={self.gh} zone={self.zone}"
        )

        while time.time() - started < duration:
            time.sleep(0.2)
            if time.time() >= next_report:
                elapsed = time.time() - started
                with self.stats.lock:
                    sent = self.stats.sent
                    responses = self.stats.responses
                    terminal = self.stats.terminal
                    fail = self.stats.publish_fail
                    top = self.stats.statuses.most_common(5)
                print(
                    f"[{elapsed:5.1f}s] sent={sent} resp={responses} terminal={terminal} "
                    f"pub_fail={fail} top={top}"
                )
                next_report += 5.0

        self._stop.set()
        for t in threads:
            t.join(timeout=2.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="MQTT stress bombard for test_node")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--gh-uid", default=DEFAULT_GH)
    parser.add_argument("--zone-uid", default=DEFAULT_ZONE)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rate", type=float, default=25.0, help="Команд в секунду суммарно")
    args = parser.parse_args()

    bombard = StressBombard(args.mqtt_host, args.mqtt_port, args.gh_uid, args.zone_uid)
    try:
        bombard.connect()
        bombard.run(args.duration, args.workers, args.rate)
    finally:
        bombard.disconnect()

    with bombard.stats.lock:
        print("\n=== STRESS SUMMARY ===")
        print(f"sent={bombard.stats.sent}")
        print(f"publish_fail={bombard.stats.publish_fail}")
        print(f"responses={bombard.stats.responses}")
        print(f"terminal={bombard.stats.terminal}")
        print(f"ack_only={bombard.stats.ack_only}")
        print(f"statuses={dict(bombard.stats.statuses)}")

    if bombard.stats.sent == 0:
        return 2
    if bombard.stats.publish_fail > bombard.stats.sent * 0.05:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
