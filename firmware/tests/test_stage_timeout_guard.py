#!/usr/bin/env python3
"""
HIL/интеграционный тест stage-timeout guard для production IRR-ноды.
"""

import argparse
import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jsonschema
import paho.mqtt.client as mqtt

COMMAND_RESPONSE_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "command_response.schema.json"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


class StageTimeoutGuardTester:
    def __init__(self, mqtt_host: str, mqtt_port: int) -> None:
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client: Optional[mqtt.Client] = None
        self.connected = threading.Event()
        self.lock = threading.Lock()
        self.command_responses: List[Tuple[str, Dict[str, object]]] = []
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
                self.command_responses.append((msg.topic, payload))
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

    def wait_response(
        self,
        *,
        cmd_id: str,
        timeout_sec: float,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, object]]:
        deadline = time.time() + timeout_sec
        expected_status = str(status or "").upper() or None
        while time.time() < deadline:
            with self.lock:
                for _, response in self.command_responses:
                    if str(response.get("cmd_id", "")) != cmd_id:
                        continue
                    actual_status = str(response.get("status", "")).upper()
                    if expected_status is None or actual_status == expected_status:
                        return response
            time.sleep(0.05)
        return None

    def wait_event(self, *, event_code: str, timeout_sec: float) -> Optional[Dict[str, object]]:
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


def expect_response(
    tester: StageTimeoutGuardTester,
    *,
    topic: str,
    cmd_id: str,
    cmd: str,
    params: Dict[str, object],
    timeout_sec: float,
    status: Optional[str] = None,
) -> Dict[str, object]:
    payload = tester.build_signed_command(cmd_id=cmd_id, cmd=cmd, params=params)
    tester.publish(topic, payload)
    response = tester.wait_response(cmd_id=cmd_id, timeout_sec=timeout_sec, status=status)
    if response is None:
        suffix = f" со статусом {status}" if status else ""
        raise RuntimeError(f"Ответ на {cmd_id}{suffix} не получен")
    schema_error = validate_command_response_schema(response)
    if schema_error:
        raise RuntimeError(f"command_response не прошёл JSON schema: {schema_error}")
    return response


def stage_flow_channels(stage: str) -> Tuple[str, str]:
    if stage == "solution_fill":
        return ("valve_clean_supply", "valve_solution_fill")
    if stage == "prepare_recirculation":
        return ("valve_solution_supply", "valve_solution_fill")
    raise ValueError(f"unsupported stage: {stage}")


def stage_timeout_event(stage: str) -> str:
    if stage == "solution_fill":
        return "solution_fill_timeout"
    if stage == "prepare_recirculation":
        return "prepare_recirculation_timeout"
    raise ValueError(f"unsupported stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser(description="HIL тест stage-timeout guard")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--gh-uid", default="gh-test-1")
    parser.add_argument("--zone-uid", default="zn-test-1")
    parser.add_argument("--node-uid", default="nd-irrig-1")
    parser.add_argument("--stage", choices=["solution_fill", "prepare_recirculation"], default="solution_fill")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--command-timeout-sec", type=float, default=4.0)
    parser.add_argument("--terminal-timeout-sec", type=float, default=12.0)
    parser.add_argument("--pre-start-wait-sec", type=float, default=5.5)
    args = parser.parse_args()

    stage_event_code = stage_timeout_event(args.stage)
    supply_channel, target_channel = stage_flow_channels(args.stage)
    pump_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/pump_main/command"
    supply_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{supply_channel}/command"
    target_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{target_channel}/command"
    storage_state_topic = f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command"

    tester = StageTimeoutGuardTester(args.mqtt_host, args.mqtt_port)
    try:
        tester.connect(
            [
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/pump_main/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{supply_channel}/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/{target_channel}/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/command_response",
                f"hydro/{args.gh_uid}/{args.zone_uid}/{args.node_uid}/storage_state/event",
            ]
        )

        cleanup_plan = [
            ("pump_main", pump_topic),
            (supply_channel, supply_topic),
            (target_channel, target_topic),
        ]
        for index, (channel, topic) in enumerate(cleanup_plan):
            cmd_id = f"hil-stage-timeout-preoff-{channel}-{index}-{int(time.time() * 1000)}"
            try:
                expect_response(
                    tester,
                    topic=topic,
                    cmd_id=cmd_id,
                    cmd="set_relay",
                    params={"state": False},
                    timeout_sec=args.command_timeout_sec,
                )
            except Exception:
                pass

        print(f"{YELLOW}Ожидание выхода из cooldown:{NC} {args.pre_start_wait_sec:.1f} сек")
        time.sleep(args.pre_start_wait_sec)

        for index, (topic, channel) in enumerate(((supply_topic, supply_channel), (target_topic, target_channel))):
            cmd_id = f"hil-stage-timeout-path-{index}-{int(time.time() * 1000)}"
            response = expect_response(
                tester,
                topic=topic,
                cmd_id=cmd_id,
                cmd="set_relay",
                params={"state": True},
                timeout_sec=args.command_timeout_sec,
            )
            if str(response.get("status", "")).upper() != "DONE":
                print(f"{RED}❌ {channel} должен завершиться DONE{NC}")
                print(json.dumps(response, ensure_ascii=False, indent=2))
                return 1

        pump_cmd_id = f"hil-stage-timeout-pump-{int(time.time() * 1000)}"
        ack = expect_response(
            tester,
            topic=pump_topic,
            cmd_id=pump_cmd_id,
            cmd="set_relay",
            params={"state": True, "timeout_ms": args.timeout_ms, "stage": args.stage},
            timeout_sec=args.command_timeout_sec,
            status="ACK",
        )
        if str(ack.get("status", "")).upper() != "ACK":
            print(f"{RED}❌ timed pump_main start должен вернуть ACK{NC}")
            print(json.dumps(ack, ensure_ascii=False, indent=2))
            return 1

        terminal = tester.wait_response(
            cmd_id=pump_cmd_id,
            status="ERROR",
            timeout_sec=max(args.terminal_timeout_sec, (args.timeout_ms / 1000.0) + 5.0),
        )
        if terminal is None:
            print(f"{RED}❌ terminal ERROR по stage timeout не получен{NC}")
            return 1

        schema_error = validate_command_response_schema(terminal)
        if schema_error:
            print(f"{RED}❌ terminal command_response не прошёл JSON schema: {schema_error}{NC}")
            print(json.dumps(terminal, ensure_ascii=False, indent=2))
            return 1

        if str(terminal.get("error_code", "")) != "stage_timeout":
            print(f"{RED}❌ ожидался error_code=stage_timeout{NC}")
            print(json.dumps(terminal, ensure_ascii=False, indent=2))
            return 1

        details = terminal.get("details")
        if not isinstance(details, dict) or details.get("stage") != args.stage or details.get("timeout_ms") != args.timeout_ms:
            print(f"{RED}❌ details terminal-ответа не содержат stage/timeout_ms{NC}")
            print(json.dumps(terminal, ensure_ascii=False, indent=2))
            return 1

        event = tester.wait_event(event_code=stage_event_code, timeout_sec=4.0)
        if event is None:
            print(f"{RED}❌ событие {stage_event_code} не получено{NC}")
            return 1

        state_cmd_id = f"hil-stage-timeout-state-{int(time.time() * 1000)}"
        state_response = expect_response(
            tester,
            topic=storage_state_topic,
            cmd_id=state_cmd_id,
            cmd="state",
            params={},
            timeout_sec=args.command_timeout_sec,
            status="DONE",
        )
        details = state_response.get("details")
        snapshot = details.get("snapshot") if isinstance(details, dict) else None
        if not isinstance(snapshot, dict):
            print(f"{RED}❌ details.snapshot отсутствует после stage timeout{NC}")
            print(json.dumps(state_response, ensure_ascii=False, indent=2))
            return 1

        for key in ("pump_main", supply_channel, target_channel):
            if snapshot.get(key) is not False:
                print(f"{RED}❌ {key} должен быть false после stage timeout{NC}")
                print(json.dumps(state_response, ensure_ascii=False, indent=2))
                return 1

        print(f"{GREEN}✅ stage timeout guard для {args.stage} отрабатывает корректно{NC}")
        print(json.dumps(terminal, ensure_ascii=False, indent=2))
        print(json.dumps(event, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"{RED}❌ {exc}{NC}")
        return 1
    finally:
        tester.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
