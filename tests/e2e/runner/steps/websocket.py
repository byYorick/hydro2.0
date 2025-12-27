"""
WebSocket step execution for E2E tests.
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class WebSocketStepExecutor:
    """Executes WebSocket-related steps in E2E scenarios."""

    def __init__(self, ws_client, schema_validator):
        self.ws_client = ws_client
        self.schema_validator = schema_validator

    async def execute_ws_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """
        Execute a WebSocket step.

        Args:
            step_type: Type of WS step
            config: Step configuration

        Returns:
            Step result
        """
        if step_type == "websocket_connect":
            return await self._execute_websocket_connect(config)
        elif step_type == "websocket_subscribe":
            return await self._execute_websocket_subscribe(config)
        elif step_type == "websocket_unsubscribe":
            return await self._execute_websocket_unsubscribe(config)
        elif step_type == "websocket_send":
            return await self._execute_websocket_send(config)
        elif step_type == "ws_subscribe_without_auth":
            return await self._execute_ws_subscribe_without_auth(config)
        else:
            raise ValueError(f"Unknown WebSocket step type: {step_type}")

    async def _execute_websocket_connect(self, config: Dict[str, Any]) -> None:
        """Connect to WebSocket."""
        await self.ws_client.connect()

    async def _execute_websocket_subscribe(self, config: Dict[str, Any]) -> None:
        """Subscribe to WebSocket channel."""
        channel = config.get("channel", "")
        self.schema_validator.validate_ws_channel_name(channel)
        await self.ws_client.subscribe(channel)

    async def _execute_websocket_unsubscribe(self, config: Dict[str, Any]) -> None:
        """Unsubscribe from WebSocket channel."""
        channel = config.get("channel", "")
        await self.ws_client.unsubscribe(channel)

    async def _execute_websocket_send(self, config: Dict[str, Any]) -> None:
        """Send message via WebSocket."""
        event = config.get("event", "")
        data = config.get("data", {})
        await self.ws_client.send(event, data)

    async def _execute_ws_subscribe_without_auth(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Try to subscribe without authentication (should fail)."""
        channel = config.get("channel", "")

        # Create a separate WS client without auth
        from ..ws_client import WSClient
        ws_no_auth = WSClient(
            url=self.ws_client.url,
            auth_token=None  # No auth token
        )

        try:
            await ws_no_auth.connect()
            await ws_no_auth.subscribe(channel)
            # If we get here, subscription succeeded (unexpected)
            await ws_no_auth.disconnect()
            return {"success": True, "error": None}
        except Exception as e:
            # Expected - subscription should fail without auth
            return {"success": False, "error": str(e)}
        finally:
            try:
                await ws_no_auth.disconnect()
            except:
                pass

    async def wait_event(self, event_type: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """
        Wait for WebSocket event.

        Args:
            event_type: Type of event to wait for
            timeout: Timeout in seconds

        Returns:
            Event data or None if timeout
        """
        return await self.ws_client.wait_event(event_type, timeout)

    async def wait_event_count(self, event_type: str, channel: Optional[str] = None,
                              timeout: float = 10.0, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Wait for multiple WebSocket events.

        Args:
            event_type: Type of events to collect
            channel: Optional channel filter
            timeout: Timeout in seconds
            filter_dict: Optional filter for events

        Returns:
            List of events collected within timeout
        """
        events = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            messages = self.ws_client.get_messages(100)
            for msg in messages:
                if self._matches_event(msg, event_type, channel, filter_dict):
                    events.append(msg)

            if events:  # Return as soon as we get at least one event
                break

            await asyncio.sleep(0.1)

        return events

    def _matches_event(self, msg: Dict[str, Any], event_type: str,
                      channel: Optional[str] = None, filter_dict: Optional[Dict[str, Any]] = None) -> bool:
        """Check if message matches event criteria."""
        # Check event type
        if msg.get("event") != event_type:
            return False

        # Check channel if specified
        if channel and msg.get("channel") != channel:
            return False

        # Check filters
        if filter_dict:
            for key, expected_value in filter_dict.items():
                if self.schema_validator.extract_json_path(msg, key) != expected_value:
                    return False

        return True
