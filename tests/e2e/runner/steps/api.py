"""
API step execution for E2E tests.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class APIStepExecutor:
    """Executes API-related steps in E2E scenarios."""

    def __init__(self, api_client, variable_resolver):
        self.api_client = api_client
        self.variable_resolver = variable_resolver

    async def execute_api_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """
        Execute an API step.

        Args:
            step_type: Type of API step (api_get, api_post, etc.)
            config: Step configuration

        Returns:
            API response data
        """
        if step_type == "api_get":
            return await self._execute_api_get(config)
        elif step_type == "api_post":
            return await self._execute_api_post(config)
        elif step_type == "api_put":
            return await self._execute_api_put(config)
        elif step_type == "api_patch":
            return await self._execute_api_patch(config)
        elif step_type == "api_delete":
            return await self._execute_api_delete(config)
        elif step_type == "api_items":
            return self._api_items(config.get("response"))
        else:
            raise ValueError(f"Unknown API step type: {step_type}")

    async def _execute_api_get(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute GET request."""
        endpoint = config.get("endpoint", "")
        params = config.get("params", {})
        save_key = config.get("save")

        response = await self.api_client.get(endpoint, params=params)

        if save_key:
            return {save_key: response}
        return response

    async def _execute_api_post(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute POST request."""
        endpoint = config.get("endpoint", "")
        data = config.get("data", {})
        save_key = config.get("save")

        response = await self.api_client.post(endpoint, json=data)

        if save_key:
            return {save_key: response}
        return response

    async def _execute_api_put(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute PUT request."""
        endpoint = config.get("endpoint", "")
        data = config.get("data", {})
        save_key = config.get("save")

        response = await self.api_client.put(endpoint, json=data)

        if save_key:
            return {save_key: response}
        return response

    async def _execute_api_patch(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute PATCH request."""
        endpoint = config.get("endpoint", "")
        data = config.get("data", {})
        save_key = config.get("save")

        response = await self.api_client.patch(endpoint, json=data)

        if save_key:
            return {save_key: response}
        return response

    async def _execute_api_delete(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute DELETE request."""
        endpoint = config.get("endpoint", "")
        save_key = config.get("save")

        response = await self.api_client.delete(endpoint)

        if save_key:
            return {save_key: response}
        return response

    def _api_items(self, response: Any) -> List[Dict[str, Any]]:
        """
        Extract items from API response.

        Args:
            response: API response

        Returns:
            List of items
        """
        if not response:
            return []

        # Handle paginated responses
        if isinstance(response, dict):
            data = response.get("data", [])

            # If data is paginated (has 'data' key with array)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            else:
                return [data] if data else []

        return []
