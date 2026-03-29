#!/usr/bin/env python3
"""
HIL/интеграционный тест контракта `storage_state/state` для production IRR-ноды.
"""

import argparse
import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import jsonschema
import paho.mqtt.client as mqtt

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "command_response.schema.json"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

EXPECTED_SNAPSHOT_KEYS = {
    "level_clean_min",
    "level_clean_max",
    "level_solution_min",
    "level_solution_max",
    "pump_main",
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
}


class StorageStateContractTester:
    def __init__(self, mqtt_host: str, mqtt_port: int) -> None:
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client: Optional[mqtt.Client] = None
        self.connected = threading.Event()
        self.lock = threading.Lock()
        self.responses: List[Dict[str, object]] = []

    def build_signed_command(self, *, cmd_id: str, cmd: str, params: Dict[str, object]) -> Dict[str, object]:
        ts = int(time.time())
        payload = {
            "cmd_id": cmd_id,
            "cmd": cmd,
            "params": params,
            "ts": ts,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        secret = os.getenv("NODE_DEFAULT_SECRET", "hydro-default-secret-key-2025")
        payload["sig"] = hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return payload

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
            self.responses.append(payload)

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

    def wait_response(self, cmd_id: str, timeout_sec: float) -> Optional[Dict[str, object]]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            with self.lock:
                for response in self.responses:
                    if str(response.get("cmd_id", "")) == cmd_id:
                        return response
            time.sleep(0.05)
        return None


def validate_schema(response: Dict[str, object]) -> Optional[str]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    try:
        jsonschema.validate(instance=response, schema=schema)
    except jsonschema.ValidationError as exc:
        return exc.message
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="HIL тест контракта storage_state/state")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--gh-uid", default="gh-test-1")
    parser.add_argument("--zone-uid", default="zn-test-1")
    parser.add_argument("--node-uid", default="nd-irrig-1")
    parser.add_argument("--timeout-sec", type=float, default=4.0)
    args = parser.parse_args()

    command_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command"
    response_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command_response"
    cmd_id = f"hil-storage-state-{int(time.time() * 1000)}"

    tester = StorageStateContractTester(args.mqtt_host, args.mqtt_port)
    try:
        tester.connect(response_topic)
        payload = tester.build_signed_command(cmd_id=cmd_id, cmd="state", params={})
        tester.publish(command_topic, payload)

        response = tester.wait_response(cmd_id, args.timeout_sec)
        if response is None:
            print(f"{RED}❌ Ответ на state не получен{NC}")
            return 1

        schema_error = validate_schema(response)
        if schema_error:
            print(f"{RED}❌ command_response не прошёл JSON schema: {schema_error}{NC}")
            return 1

        status = str(response.get("status", "")).upper()
        if status != "DONE":
            print(f"{RED}❌ Ожидался DONE, получен {status}{NC}")
            return 1

        details = response.get("details")
        if not isinstance(details, dict):
            print(f"{RED}❌ details отсутствует или не объект{NC}")
            return 1

        snapshot = details.get("snapshot")
        legacy_state = details.get("state")
        if not isinstance(snapshot, dict):
            print(f"{RED}❌ details.snapshot отсутствует или не объект{NC}")
            return 1
        if not isinstance(legacy_state, dict):
            print(f"{RED}❌ details.state отсутствует или не объект{NC}")
            return 1

        missing_snapshot_keys = sorted(EXPECTED_SNAPSHOT_KEYS - set(snapshot.keys()))
        if missing_snapshot_keys:
            print(f"{RED}❌ В snapshot отсутствуют ключи: {missing_snapshot_keys}{NC}")
            return 1

        for field in ("sample_ts", "age_sec", "max_age_sec", "is_fresh"):
            if field not in details:
                print(f"{RED}❌ В details отсутствует поле {field}{NC}")
                return 1

        if details["age_sec"] != 0:
            print(f"{RED}❌ age_sec должен быть 0, получено {details['age_sec']}{NC}")
            return 1
        if details["is_fresh"] is not True:
            print(f"{RED}❌ is_fresh должен быть true{NC}")
            return 1

        print(f"{GREEN}✅ storage_state/state контракт корректен{NC}")
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0
    finally:
        tester.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
