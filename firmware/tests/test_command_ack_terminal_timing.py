#!/usr/bin/env python3
"""
HIL/интеграционный тест таймингов ACK -> terminal для test_node.

Проверяет:
1) По cmd_id приходят оба статуса: ACK и terminal.
2) ACK приходит раньше terminal.
3) Разница времени между ACK и terminal близка к sim_delay_ms.
"""

import argparse
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

TERMINAL_STATUSES = {"DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT"}


@dataclass
class ReceivedMessage:
    topic: str
    payload: Dict[str, object]
    received_at: float


class AckTerminalTimingTester:
    def __init__(self, mqtt_host: str, mqtt_port: int):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client: Optional[mqtt.Client] = None
        self.lock = threading.Lock()
        self.command_responses: List[ReceivedMessage] = []
        self.connected = threading.Event()

    def build_signed_command(self, cmd_id: str, cmd: str, params: Dict[str, object]) -> Dict[str, object]:
        ts = int(time.time())
        base_payload = {
            "cmd_id": cmd_id,
            "cmd": cmd,
            "params": params,
            "ts": ts,
        }
        canonical = json.dumps(base_payload, sort_keys=True, separators=(",", ":"))
        secret = os.getenv("NODE_DEFAULT_SECRET", "hydro-default-secret-key-2025")
        sig = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        base_payload["sig"] = sig
        return base_payload

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected.set()
            print(f"{GREEN}✅ Подключено к MQTT брокеру{NC}")
        else:
            print(f"{RED}❌ Ошибка подключения к MQTT: {rc}{NC}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        with self.lock:
            self.command_responses.append(
                ReceivedMessage(topic=msg.topic, payload=payload, received_at=time.time())
            )

    def connect(self, response_topic: str) -> None:
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_start()
        if not self.connected.wait(timeout=5):
            raise RuntimeError("MQTT connect timeout")
        self.client.subscribe(response_topic, qos=1)
        print(f"{YELLOW}Подписка:{NC} {response_topic}")

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()

    def publish(self, topic: str, payload: Dict[str, object]) -> None:
        assert self.client is not None
        self.client.publish(topic, json.dumps(payload), qos=1)
        print(f"{YELLOW}Отправлена команда:{NC} {topic}")
        print(json.dumps(payload, ensure_ascii=False))

    def find_ack_and_terminal(self, cmd_id: str) -> Tuple[Optional[ReceivedMessage], Optional[ReceivedMessage]]:
        with self.lock:
            related = [m for m in self.command_responses if str(m.payload.get("cmd_id", "")) == cmd_id]
        if not related:
            return None, None
        ack = None
        terminal = None
        for msg in related:
            status = str(msg.payload.get("status", "")).upper()
            if status == "ACK" and ack is None:
                ack = msg
            if status in TERMINAL_STATUSES:
                if terminal is None or msg.received_at < terminal.received_at:
                    terminal = msg
        return ack, terminal


def main() -> int:
    parser = argparse.ArgumentParser(description="HIL тест таймингов ACK -> terminal")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--gh-uid", default="gh-test-1")
    parser.add_argument("--zone-uid", default="zn-test-1")
    parser.add_argument("--node-uid", default="nd-test-001")
    parser.add_argument("--channel", default="ph_sensor")
    parser.add_argument("--cmd", default="set_relay")
    parser.add_argument("--sim-delay-ms", type=int, default=1200)
    parser.add_argument("--sim-status", default="DONE")
    parser.add_argument("--ack-timeout-sec", type=float, default=3.0)
    parser.add_argument("--terminal-timeout-sec", type=float, default=12.0)
    parser.add_argument("--lower-jitter-ms", type=int, default=200)
    parser.add_argument("--upper-jitter-ms", type=int, default=1500)
    args = parser.parse_args()

    command_topic = (
        f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{args.channel}/command"
    )
    response_topic = (
        f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{args.channel}/command_response"
    )
    cmd_id = f"hil-timing-{int(time.time() * 1000)}"

    params: Dict[str, object] = {
        "state": True,
        "sim_delay_ms": args.sim_delay_ms,
        "sim_status": str(args.sim_status).upper(),
    }

    tester = AckTerminalTimingTester(args.mqtt_host, args.mqtt_port)
    try:
        tester.connect(response_topic=response_topic)
        payload = tester.build_signed_command(cmd_id=cmd_id, cmd=args.cmd, params=params)
        tester.publish(command_topic, payload)

        ack: Optional[ReceivedMessage] = None
        terminal: Optional[ReceivedMessage] = None

        ack_deadline = time.time() + args.ack_timeout_sec
        while time.time() < ack_deadline and ack is None:
            ack, terminal = tester.find_ack_and_terminal(cmd_id)
            if ack is None:
                time.sleep(0.05)

        if ack is None:
            print(f"{RED}❌ ACK не получен в течение {args.ack_timeout_sec}с{NC}")
            return 1

        print(f"{GREEN}✅ ACK получен{NC}: status={ack.payload.get('status')} at={ack.received_at:.3f}")

        term_deadline = time.time() + args.terminal_timeout_sec
        while time.time() < term_deadline and terminal is None:
            _, terminal = tester.find_ack_and_terminal(cmd_id)
            if terminal is None:
                time.sleep(0.05)

        if terminal is None:
            print(f"{RED}❌ Terminal статус не получен в течение {args.terminal_timeout_sec}с{NC}")
            return 1

        terminal_status = str(terminal.payload.get("status", "")).upper()
        if terminal_status not in TERMINAL_STATUSES:
            print(f"{RED}❌ Получен не-terminal статус: {terminal_status}{NC}")
            return 1

        gap_ms = int((terminal.received_at - ack.received_at) * 1000)
        min_expected = max(0, args.sim_delay_ms - args.lower_jitter_ms)
        max_expected = args.sim_delay_ms + args.upper_jitter_ms

        print(
            f"{YELLOW}ACK->terminal:{NC} gap={gap_ms}ms, expected=[{min_expected}..{max_expected}]ms, "
            f"terminal={terminal_status}"
        )

        if gap_ms < min_expected or gap_ms > max_expected:
            print(f"{RED}❌ Тайминг вне допуска{NC}")
            return 1

        if terminal.received_at < ack.received_at:
            print(f"{RED}❌ Нарушен порядок статусов: terminal раньше ACK{NC}")
            return 1

        print(f"{GREEN}✅ HIL тайминг ACK->terminal прошёл{NC}")
        return 0
    finally:
        tester.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
