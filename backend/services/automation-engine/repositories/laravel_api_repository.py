"""Laravel write API wrapper + SQL read-model adapter for effective targets."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from common.env import get_settings
from common.http_client_pool import make_request
from repositories.effective_targets_sql_read_model import EffectiveTargetsSqlReadModel

logger = logging.getLogger(__name__)


class LaravelApiRepository:
    """
    Контракт класса сохранен:
    - read-path effective targets: direct SQL (без runtime HTTP);
    - write-path grow-cycle actions: Laravel internal API.
    """

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.laravel_api_url or "http://laravel"
        self.api_token = self.settings.laravel_api_token
        cache_ttl = float(os.getenv("EFFECTIVE_TARGETS_CACHE_TTL_SEC", "30"))
        self._effective_targets_reader = EffectiveTargetsSqlReadModel(cache_ttl_sec=cache_ttl)

        if not self.api_token:
            logger.warning("LARAVEL_API_TOKEN not configured, internal write API calls may fail")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def get_effective_targets_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        return await self._effective_targets_reader.get_effective_targets_batch(zone_ids)

    async def get_effective_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        return await self._effective_targets_reader.get_effective_targets(zone_id)

    async def advance_grow_cycle_phase(self, grow_cycle_id: int) -> bool:
        """Продвинуть фазу цикла выращивания через Laravel internal API."""
        url = f"{self.base_url}/api/internal/grow-cycles/{grow_cycle_id}/advance-phase"
        try:
            response = await make_request(
                "post",
                url,
                endpoint="advance_grow_cycle_phase",
                headers=self._get_headers(),
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "ok"
            logger.error(
                "Laravel API advance phase failed: HTTP %s - %s",
                response.status_code,
                response.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("Error calling Laravel API (advance phase): %s", exc, exc_info=True)
            return False

    async def harvest_grow_cycle(self, grow_cycle_id: int) -> bool:
        """Завершить цикл выращивания через Laravel internal API."""
        url = f"{self.base_url}/api/internal/grow-cycles/{grow_cycle_id}/harvest"
        try:
            response = await make_request(
                "post",
                url,
                endpoint="harvest_grow_cycle",
                headers=self._get_headers(),
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "ok"
            logger.error(
                "Laravel API harvest failed: HTTP %s - %s",
                response.status_code,
                response.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("Error calling Laravel API (harvest): %s", exc, exc_info=True)
            return False
