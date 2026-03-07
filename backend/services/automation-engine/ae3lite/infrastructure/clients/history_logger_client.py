"""Thin AE3-Lite client for history-logger command publish."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import httpx

from ae3lite.domain.errors import CommandPublishError


class HistoryLoggerClient:
    """Publishes commands only through history-logger `/commands`."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        source: str = "automation-engine",
        timeout_sec: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = str(base_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")).rstrip("/")
        self._token = str(token or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN") or "").strip()
        self._source = source
        self._timeout_sec = float(timeout_sec)
        self._client = client

    async def publish(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Mapping[str, Any],
        cmd_id: Optional[str] = None,
    ) -> str:
        payload = {
            "greenhouse_uid": greenhouse_uid,
            "zone_id": zone_id,
            "node_uid": node_uid,
            "channel": channel,
            "cmd": cmd,
            "params": dict(params),
            "source": self._source,
        }
        if cmd_id:
            payload["cmd_id"] = cmd_id
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = await self._post("/commands", payload, headers)
        if response.status_code != 200:
            raise CommandPublishError(self._extract_error_message(response))

        try:
            body = response.json()
        except ValueError as exc:
            raise CommandPublishError("history-logger returned invalid JSON") from exc

        command_id = str(((body.get("data") or {}) if isinstance(body, dict) else {}).get("command_id") or "").strip()
        if not command_id:
            raise CommandPublishError("history-logger response does not contain data.command_id")
        return command_id

    async def _post(self, path: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(f"{self._base_url}{path}", json=dict(payload), headers=dict(headers))
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            return await client.post(f"{self._base_url}{path}", json=dict(payload), headers=dict(headers))

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or payload.get("message") or "").strip()
            if detail:
                return detail
        text = str(response.text or "").strip()
        if text:
            return text
        return f"history-logger publish failed with HTTP {response.status_code}"
