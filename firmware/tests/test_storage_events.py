#!/usr/bin/env python3
"""
HIL/интеграционный тест `storage_state/event` для production IRR-ноды.
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

COMMAND_RESPONSE_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "command_response.schema.json"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


EXPECTED_EVENT_SNAPSHOT_KEYS = {
    "pump_main",
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
}


class StorageEventTester:
    def __init__(self, mqtt_host: str, mqtt_port: int) -> None:
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client: Optional[mqtt.Client] = None
        self.connected = threading.Event()
        self.lock = threading.Lock()
        self.command_responses: List[Dict[str, object]] = []
        self.events: List[Dict[str, object]] = []

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
            if msg.topic.endswith("/command_response"):
                self.command_responses.append(payload)
            elif msg.topic.endswith("/event"):
                self.events.append(payload)

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

    def wait_command_response(self, cmd_id: str, timeout_sec: float) -> Optional[Dict[str, object]]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            with self.lock:
                for response in self.command_responses:
                    if str(response.get("cmd_id", "")) == cmd_id:
                        return response
            time.sleep(0.05)
        return None

    def wait_event(self, event_code: str, timeout_sec: float) -> Optional[Dict[str, object]]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            with self.lock:
                for event in self.events:
                    if str(event.get("event_code", "")) == event_code:
                        return event
            time.sleep(0.05)
        return None


def validate_command_response_schema(response: Dict[str, object]) -> Optional[str]:
    with open(COMMAND_RESPONSE_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    try:
        jsonschema.validate(instance=response, schema=schema)
    except jsonschema.ValidationError as exc:
        return exc.message
    return None


def expect_command_response(
    tester: StorageEventTester,
    *,
    topic: str,
    cmd_id: str,
    cmd: str,
    params: Dict[str, object],
    timeout_sec: float,
) -> Dict[str, object]:
    payload = tester.build_signed_command(cmd_id=cmd_id, cmd=cmd, params=params)
    tester.publish(topic, payload)
    response = tester.wait_command_response(cmd_id, timeout_sec)
    if response is None:
        raise RuntimeError(f"Ответ на {cmd_id} не получен")
    schema_error = validate_command_response_schema(response)
    if schema_error:
        raise RuntimeError(f"command_response не прошёл JSON schema: {schema_error}")
    return response


def validate_event_payload(event: Dict[str, object], *, event_code: str, required_sensor_flag: str) -> Optional[str]:
    if str(event.get("event_code", "")) != event_code:
        return f"unexpected event_code: {event.get('event_code')}"
    if not isinstance(event.get("ts"), int):
        return "ts отсутствует или не integer"

    snapshot = event.get("snapshot")
    if not isinstance(snapshot, dict):
        return "snapshot отсутствует или не объект"

    missing_keys = sorted(EXPECTED_EVENT_SNAPSHOT_KEYS - set(snapshot.keys()))
    if missing_keys:
        return f"в snapshot отсутствуют actuator keys: {missing_keys}"

    if snapshot.get(required_sensor_flag) is not True:
        return f"{required_sensor_flag} должен быть true в snapshot"

    state = event.get("state")
    if not isinstance(state, dict):
        return "state отсутствует или не объект"

    if state.get(required_sensor_flag) not in (True, 1):
        return f"{required_sensor_flag} должен быть true/1 в state"

    return None


def validate_solution_fill_latched(snapshot: Dict[str, object]) -> Optional[str]:
    expected_on = ("pump_main", "valve_clean_supply", "valve_solution_fill")
    for key in expected_on:
        if snapshot.get(key) is not True:
            return f"{key} должен оставаться true после solution_fill_completed"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="HIL тест storage_state/event")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--gh-uid", default="gh-test-1")
    parser.add_argument("--zone-uid", default="zn-test-1")
    parser.add_argument("--node-uid", default="nd-irrig-1")
    parser.add_argument("--event-code", choices=["clean_fill_completed", "solution_fill_completed"], default="clean_fill_completed")
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--command-timeout-sec", type=float, default=4.0)
    args = parser.parse_args()

    event_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/event"
    storage_state_response_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command_response"

    tester = StorageEventTester(args.mqtt_host, args.mqtt_port)
    try:
        subscriptions = [event_topic, storage_state_response_topic]
        command_plan = []
        sensor_flag = ""

        if args.event_code == "clean_fill_completed":
            subscriptions.append(f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/valve_clean_fill/command_response")
            command_plan = [
                ("valve_clean_fill", {"state": False}),
                ("valve_clean_fill", {"state": True}),
            ]
            sensor_flag = "level_clean_max"
        else:
            subscriptions.extend([
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/pump_main/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/valve_clean_supply/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/valve_solution_fill/command_response",
            ])
            command_plan = [
                ("pump_main", {"state": False}),
                ("valve_clean_supply", {"state": False}),
                ("valve_solution_fill", {"state": False}),
                ("valve_clean_supply", {"state": True}),
                ("valve_solution_fill", {"state": True}),
                ("pump_main", {"state": True}),
            ]
            sensor_flag = "level_solution_max"

        tester.connect(subscriptions)

        for idx, (channel, params) in enumerate(command_plan):
            cmd_id = f"hil-event-{args.event_code}-{idx}-{int(time.time() * 1000)}"
            topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{channel}/command"
            response = expect_command_response(
                tester,
                topic=topic,
                cmd_id=cmd_id,
                cmd="set_relay",
                params=params,
                timeout_sec=args.command_timeout_sec,
            )

            expected_status = "DONE"
            actual_status = str(response.get("status", "")).upper()
            if actual_status != expected_status:
                raise RuntimeError(f"{channel}/set_relay ожидал {expected_status}, получен {actual_status}")

            time.sleep(0.25)

        print(f"{YELLOW}Ожидание события:{NC} {args.event_code} (timeout {args.timeout_sec:.1f} сек)")
        event = tester.wait_event(args.event_code, args.timeout_sec)
        if event is None:
            print(f"{RED}❌ Событие {args.event_code} не получено за timeout{NC}")
            print(f"{YELLOW}Примечание:{NC} для green-прохода соответствующий *_max датчик должен физически перейти в true во время активного fill-path")
            return 1

        event_error = validate_event_payload(event, event_code=args.event_code, required_sensor_flag=sensor_flag)
        if event_error:
            print(f"{RED}❌ Некорректный payload события: {event_error}{NC}")
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 1

        if args.event_code == "solution_fill_completed":
            state_cmd = f"hil-state-{int(time.time() * 1000)}"
            state_response = expect_command_response(
                tester,
                topic=f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command",
                cmd_id=state_cmd,
                cmd="state",
                params={},
                timeout_sec=args.command_timeout_sec,
            )
            if str(state_response.get("status", "")).upper() != "DONE":
                print(f"{RED}❌ storage_state/state должен завершиться DONE{NC}")
                print(json.dumps(state_response, ensure_ascii=False, indent=2))
                return 1

            details = state_response.get("details")
            snapshot = details.get("snapshot") if isinstance(details, dict) else None
            if not isinstance(snapshot, dict):
                print(f"{RED}❌ details.snapshot отсутствует или не объект{NC}")
                print(json.dumps(state_response, ensure_ascii=False, indent=2))
                return 1

            latch_error = validate_solution_fill_latched(snapshot)
            if latch_error:
                print(f"{RED}❌ {latch_error}{NC}")
                print(json.dumps(state_response, ensure_ascii=False, indent=2))
                return 1

        print(f"{GREEN}✅ storage_state/event {args.event_code} отрабатывает корректно{NC}")
        print(json.dumps(event, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"{RED}❌ {exc}{NC}")
        return 1
    finally:
        tester.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
