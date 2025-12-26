"""
Laravel API Repository - доступ к данным через Laravel API вместо прямых SQL запросов.
Использует новую модель GrowCycle вместо legacy таблиц.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from common.env import get_settings
from common.http_client_pool import make_request

logger = logging.getLogger(__name__)


class LaravelApiRepository:
    """Репозиторий для работы с Laravel API."""
    
    def __init__(self):
        """Инициализация репозитория."""
        self.settings = get_settings()
        self.base_url = self.settings.laravel_api_url or 'http://laravel'
        self.api_token = self.settings.laravel_api_token
        
        if not self.api_token:
            logger.warning('LARAVEL_API_TOKEN not configured, API calls may fail')
    
    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        return headers
    
    async def get_effective_targets_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить effective targets для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
            
        Returns:
            Dict[zone_id, effective_targets] или None если цикла нет
            
        Raises:
            httpx.RequestError: При ошибках HTTP запроса
        """
        if not zone_ids:
            return {}
        
        url = f"{self.base_url}/api/internal/effective-targets/batch"
        payload = {
            'zone_ids': zone_ids,
        }
        
        try:
            response = await make_request(
                'post',
                url,
                endpoint='effective_targets_batch',
                json=payload,
                headers=self._get_headers(),
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'ok':
                    return data.get('data', {})
                else:
                    logger.error(f'Laravel API returned error status: {data.get("message")}')
                    return {}
            elif response.status_code == 401:
                logger.error('Laravel API authentication failed - check LARAVEL_API_TOKEN')
                return {}
            elif response.status_code == 422:
                errors = response.json().get('errors', {})
                logger.error(f'Laravel API validation failed: {errors}')
                return {}
            else:
                logger.error(
                    f'Laravel API request failed: HTTP {response.status_code} - {response.text[:200]}'
                )
                return {}
                    
        except Exception as e:
            logger.error(f'Error calling Laravel API: {e}', exc_info=True)
            return {}
    
    async def get_effective_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить effective targets для одной зоны.
        
        Args:
            zone_id: ID зоны
            
        Returns:
            Dict с effective targets или None если цикла нет
        """
        results = await self.get_effective_targets_batch([zone_id])
        return results.get(zone_id)

