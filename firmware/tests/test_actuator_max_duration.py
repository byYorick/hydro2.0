#!/usr/bin/env python3
"""
HIL/интеграционный тест latched `set_relay` для production IRR-ноды.
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


class ActuatorMaxDurationTester:
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

    def connect(self, topics: List[str]) -> None:
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_start()
        if not self.connected.wait(timeout=5):
            raise RuntimeError("MQTT connect timeout")
        for topic in topics:
            self.client.subscribe(topic, qos=1)
            print(f"{YELLOW}Подписка:{NC} {topic}")

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


def expect_response(
    tester: ActuatorMaxDurationTester,
    *,
    topic: str,
    cmd_id: str,
    cmd: str,
    params: Dict[str, object],
    timeout_sec: float,
) -> Dict[str, object]:
    payload = tester.build_signed_command(cmd_id=cmd_id, cmd=cmd, params=params)
    tester.publish(topic, payload)
    response = tester.wait_response(cmd_id, timeout_sec)
    if response is None:
        raise RuntimeError(f"Ответ на {cmd_id} не получен")
    schema_error = validate_schema(response)
    if schema_error:
        raise RuntimeError(f"command_response не прошёл JSON schema: {schema_error}")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="HIL тест latched set_relay")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--gh-uid", default="gh-test-1")
    parser.add_argument("--zone-uid", default="zn-test-1")
    parser.add_argument("--node-uid", default="nd-irrig-1")
    parser.add_argument("--channel", default="valve_solution_supply")
    parser.add_argument("--timeout-sec", type=float, default=4.0)
    parser.add_argument("--hold-sec", type=float, default=33.0)
    parser.add_argument("--pre-start-wait-sec", type=float, default=5.5)
    args = parser.parse_args()

    actuator_command_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{args.channel}/command"
    actuator_response_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{args.channel}/command_response"
    state_command_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command"
    state_response_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command_response"

    tester = ActuatorMaxDurationTester(args.mqtt_host, args.mqtt_port)
    try:
        tester.connect([actuator_response_topic, state_response_topic])

        pre_off_cmd = f"hil-maxdur-preoff-{int(time.time() * 1000)}"
        try:
            expect_response(
                tester,
                topic=actuator_command_topic,
                cmd_id=pre_off_cmd,
                cmd="set_relay",
                params={"state": False},
                timeout_sec=args.timeout_sec,
            )
        except Exception:
            pass

        print(f"{YELLOW}Ожидание выхода из cooldown:{NC} {args.pre_start_wait_sec:.1f} сек")
        time.sleep(args.pre_start_wait_sec)

        on_cmd = f"hil-maxdur-on-{int(time.time() * 1000)}"
        on_response = expect_response(
            tester,
            topic=actuator_command_topic,
            cmd_id=on_cmd,
            cmd="set_relay",
            params={"state": True},
            timeout_sec=args.timeout_sec,
        )
        if str(on_response.get("status", "")).upper() != "DONE":
            print(f"{RED}❌ ON должен завершиться DONE{NC}")
            print(json.dumps(on_response, ensure_ascii=False, indent=2))
            return 1

        print(f"{YELLOW}Удержание канала во включенном состоянии:{NC} {args.hold_sec:.1f} сек")
        time.sleep(args.hold_sec)

        state_cmd = f"hil-maxdur-state-{int(time.time() * 1000)}"
        state_response = expect_response(
            tester,
            topic=state_command_topic,
            cmd_id=state_cmd,
            cmd="state",
            params={},
            timeout_sec=args.timeout_sec,
        )
        if str(state_response.get("status", "")).upper() != "DONE":
            print(f"{RED}❌ storage_state/state должен завершиться DONE{NC}")
            print(json.dumps(state_response, ensure_ascii=False, indent=2))
            return 1

        details = state_response.get("details")
        if not isinstance(details, dict):
            print(f"{RED}❌ details отсутствует или не объект{NC}")
            return 1

        snapshot = details.get("snapshot")
        if not isinstance(snapshot, dict):
            print(f"{RED}❌ details.snapshot отсутствует или не объект{NC}")
            return 1

        state_value = snapshot.get(args.channel)
        if state_value is not True:
            print(f"{RED}❌ Ожидался latched ON для канала {args.channel}, получено {state_value}{NC}")
            print(json.dumps(state_response, ensure_ascii=False, indent=2))
            return 1

        off_cmd = f"hil-latched-off-{int(time.time() * 1000)}"
        off_response = expect_response(
            tester,
            topic=actuator_command_topic,
            cmd_id=off_cmd,
            cmd="set_relay",
            params={"state": False},
            timeout_sec=args.timeout_sec,
        )
        if str(off_response.get("status", "")).upper() != "DONE":
            print(f"{RED}❌ OFF должен завершиться DONE{NC}")
            print(json.dumps(off_response, ensure_ascii=False, indent=2))
            return 1

        print(f"{GREEN}✅ latched set_relay для {args.channel} отрабатывает корректно{NC}")
        print(json.dumps(state_response, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"{RED}❌ {exc}{NC}")
        return 1
    finally:
        tester.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
