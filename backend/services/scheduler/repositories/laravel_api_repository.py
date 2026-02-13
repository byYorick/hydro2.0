"""
Laravel API Repository for scheduler.
Fetches effective targets batch via Laravel internal API.
"""
import logging
from typing import Any, Dict, List

from common.env import get_settings
from common.http_client_pool import make_request

logger = logging.getLogger(__name__)


class LaravelApiRepository:
    """Репозиторий для работы с Laravel API в scheduler."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.laravel_api_url or "http://laravel"
        self.api_token = settings.laravel_api_token

        if not self.api_token:
            logger.warning("LARAVEL_API_TOKEN not configured, API calls may fail")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    @staticmethod
    def _normalize_zone_keys(data: Dict[str, Any]) -> Dict[Any, Any]:
        normalized: Dict[Any, Any] = {}
        for key, value in (data or {}).items():
            try:
                normalized[int(key)] = value
            except (TypeError, ValueError):
                normalized[key] = value
        return normalized

    async def get_effective_targets_batch(self, zone_ids: List[int]) -> Dict[int, Any]:
        if not zone_ids:
            return {}

        url = f"{self.base_url}/api/internal/effective-targets/batch"
        payload = {"zone_ids": zone_ids}

        try:
            response = await make_request(
                "post",
                url,
                endpoint="effective_targets_batch",
                json=payload,
                headers=self._get_headers(),
            )
        except Exception as exc:
            logger.error("Failed to call Laravel API: %s", exc, exc_info=True)
            return {}

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                return self._normalize_zone_keys(data.get("data", {}))
            logger.error("Laravel API returned error status: %s", data.get("message"))
            return {}

        if response.status_code == 401:
            logger.error("Laravel API authentication failed - check LARAVEL_API_TOKEN")
            return {}

        logger.error(
            "Laravel API request failed: HTTP %s - %s",
            response.status_code,
            response.text[:200],
        )
        return {}
