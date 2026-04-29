"""Разовая проверка доступности узла через status/LWT MQTT-топики."""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

import paho.mqtt.client as mqtt

from common.env import get_settings

logger = logging.getLogger(__name__)


def _status_and_ts(payload_obj: Any) -> Tuple[Optional[str], Optional[int]]:
    if not isinstance(payload_obj, dict):
        return None, None

    status_raw = payload_obj.get("status")
    status = status_raw.strip().upper() if isinstance(status_raw, str) and status_raw.strip() else None

    ts_raw = payload_obj.get("ts")
    ts: Optional[int] = None
    if isinstance(ts_raw, (int, float)):
        ts = int(ts_raw)
    elif isinstance(ts_raw, str):
        try:
            ts = int(float(ts_raw.strip()))
        except (TypeError, ValueError):
            ts = None

    return status, ts


def probe_node_status(
    greenhouse_uid: str,
    zone_segment: str,
    node_uid: str,
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
    """
    Проверяет «живую» доступность узла без БД:
    - читает retained `.../status` и `.../lwt`;
    - учитывает `status=ONLINE` + свежесть `ts`;
    - OFFLINE в LWT/status перевешивает stale ONLINE.
    """
    topic = f"hydro/{greenhouse_uid}/{zone_segment}/{node_uid}/status"
    lwt_topic = f"hydro/{greenhouse_uid}/{zone_segment}/{node_uid}/lwt"
    heartbeat_topic = f"hydro/{greenhouse_uid}/{zone_segment}/{node_uid}/heartbeat"
    telemetry_topic = f"hydro/{greenhouse_uid}/{zone_segment}/{node_uid}/+/telemetry"
    s = get_settings()
    wait_sec = max(1.0, min(float(timeout_sec), 15.0))
    fresh_window_sec = max(15, int(getattr(s, "node_offline_timeout_sec", 120)))
    result: Dict[str, Any] = {
        "topic": topic,
        "lwt_topic": lwt_topic,
        "heartbeat_topic": heartbeat_topic,
        "telemetry_topic": telemetry_topic,
        "reachable": False,
        "retained": None,  # retained-флаг для status сообщения
        "status_ts": None,
        "status_age_sec": None,
        "fresh_window_sec": fresh_window_sec,
        "raw_payload": None,
        "payload": None,
        "lwt_payload": None,
        "live_signal_topic": None,
        "reason": None,
        "mqtt_status": None,
        "lwt_status": None,
    }
    evt = threading.Event()
    lock = threading.Lock()

    def on_connect(client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            client.subscribe(topic, qos=1)
            client.subscribe(lwt_topic, qos=1)
            client.subscribe(heartbeat_topic, qos=1)
            client.subscribe(telemetry_topic, qos=1)

    def on_message(client, userdata, msg):  # noqa: ANN001
        with lock:
            try:
                raw = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                raw = ""

            parsed: Any = None
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = {"raw": raw}

            is_status_topic = msg.topic == topic
            is_lwt_topic = msg.topic == lwt_topic
            is_heartbeat_topic = msg.topic == heartbeat_topic
            is_telemetry_topic = msg.topic.endswith("/telemetry") and msg.topic.startswith(
                f"hydro/{greenhouse_uid}/{zone_segment}/{node_uid}/"
            )
            decisive = False

            if is_status_topic:
                result["retained"] = bool(msg.retain)
                result["raw_payload"] = raw
                result["payload"] = parsed

                mqtt_status, ts = _status_and_ts(parsed)
                if mqtt_status:
                    result["mqtt_status"] = mqtt_status
                if ts is not None:
                    result["status_ts"] = ts
                    age = int(max(0, time.time() - ts))
                    result["status_age_sec"] = age

                # Надёжный ONLINE: либо live-сообщение (retain=False), либо свежий retained с ts.
                # Для "реально сейчас доступна" retained ONLINE сам по себе недостаточен:
                # ждём живой сигнал в окне probe (status non-retained / heartbeat / telemetry).
                if result["mqtt_status"] == "ONLINE":
                    if result["retained"] is False:
                        result["reachable"] = True
                        result["live_signal_topic"] = msg.topic
                        result["reason"] = None
                        decisive = True
                    elif isinstance(result.get("status_age_sec"), int):
                        if result["status_age_sec"] <= fresh_window_sec:
                            result["reachable"] = False
                            result["reason"] = "retained_online_waiting_live_signal"
                        else:
                            result["reachable"] = False
                            result["reason"] = "stale_status"
                    else:
                        result["reachable"] = False
                        result["reason"] = "status_ts_missing"
                elif result["mqtt_status"] == "OFFLINE":
                    result["reachable"] = False
                    result["reason"] = "status_offline"
                    decisive = True

            elif is_lwt_topic:
                result["lwt_payload"] = parsed if parsed is not None else raw
                lwt_status: Optional[str] = None
                if isinstance(parsed, dict):
                    val = parsed.get("status")
                    if isinstance(val, str):
                        lwt_status = val.strip().upper() or None
                elif isinstance(parsed, str):
                    lwt_status = parsed.strip().upper() or None
                elif isinstance(raw, str):
                    lwt_status = raw.strip().upper() or None

                if lwt_status:
                    result["lwt_status"] = lwt_status

                if result["lwt_status"] == "OFFLINE":
                    result["reachable"] = False
                    result["reason"] = "offline_lwt"
                    decisive = True

            elif is_heartbeat_topic or is_telemetry_topic:
                # Любой не-retained heartbeat/telemetry во время probe = узел реально живой сейчас.
                if not bool(msg.retain):
                    result["reachable"] = True
                    result["live_signal_topic"] = msg.topic
                    result["reason"] = None
                    decisive = True

            # Не держим probe дольше, если уже получили надёжный вывод.
            if decisive:
                evt.set()

    client_id = f"hydro-live-status-{(int(time.time() * 1000) % 1_000_000_000)}"
    client = mqtt.Client(client_id=client_id, clean_session=True)
    if s.mqtt_user:
        client.username_pw_set(s.mqtt_user, s.mqtt_pass or None)
    if s.mqtt_tls:
        if s.mqtt_ca_file:
            client.tls_set(ca_certs=s.mqtt_ca_file)
        else:
            client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(s.mqtt_host, s.mqtt_port, keepalive=min(30, int(wait_sec) + 10))
        client.loop_start()
        if not evt.wait(timeout=wait_sec):
            # Если не было убедительного сигнала — возвращаем наиболее информативную причину.
            if result.get("reason") in (None, ""):
                has_status_message = result.get("payload") is not None
                if not has_status_message:
                    result["reason"] = "timeout"
                elif result.get("mqtt_status") == "ONLINE":
                    # ONLINE есть, но не доказали "живость" в allowed window.
                    result["reason"] = result.get("reason") or "retained_online_waiting_live_signal"
                else:
                    result["reason"] = "inconclusive"
    except Exception as e:
        logger.warning("probe_node_status MQTT error: %s", e, exc_info=True)
        result["reason"] = "mqtt_error"
        result["error"] = str(e)
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    # Подстраховка: если за время probe пришёл OFFLINE в LWT, online-result недействителен.
    if result.get("lwt_status") == "OFFLINE":
        result["reachable"] = False
        result["reason"] = "offline_lwt"

    return result
