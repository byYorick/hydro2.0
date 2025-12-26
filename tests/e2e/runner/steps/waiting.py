"""
Waiting and assertion steps for E2E tests.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WaitingStepExecutor:
    """Executes waiting and assertion steps in E2E scenarios."""

    def __init__(self, variable_resolver):
        self.variable_resolver = variable_resolver

    async def execute_waiting_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """
        Execute a waiting step.

        Args:
            step_type: Type of waiting step
            config: Step configuration

        Returns:
            Step result
        """
        if step_type == "sleep":
            return await self._execute_sleep(config)
        elif step_type == "wait_until":
            return await self._execute_wait_until(config)
        elif step_type == "eventually":
            return await self._execute_eventually(config)
        else:
            raise ValueError(f"Unknown waiting step type: {step_type}")

    async def _execute_sleep(self, config: Dict[str, Any]) -> None:
        """Execute sleep step."""
        seconds = config.get("seconds", config.get("timeout", 1.0))
        await asyncio.sleep(float(seconds))

    async def _execute_wait_until(self, config: Dict[str, Any]) -> Any:
        """
        Wait until condition becomes true.

        Example:
        - step: wait_for_zone_online
          type: wait_until
          condition: "zone_id in context and context.get('zone_status') == 'online'"
          timeout: 30.0
          interval: 1.0
        """
        condition_expr = config.get("condition", "")
        timeout = config.get("timeout", 30.0)
        interval = config.get("interval", 1.0)
        max_attempts = config.get("max_attempts")

        if not condition_expr:
            raise ValueError("wait_until requires 'condition' parameter")

        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                # Evaluate condition
                if self._evaluate_condition(condition_expr):
                    return True

            except Exception as e:
                logger.debug(f"Condition evaluation failed: {e}")

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Condition '{condition_expr}' not met within {timeout}s")

            # Check max attempts
            if max_attempts:
                attempts = int(elapsed / interval) + 1
                if attempts >= max_attempts:
                    raise TimeoutError(f"Condition '{condition_expr}' not met after {max_attempts} attempts")

            await asyncio.sleep(interval)

    async def _execute_eventually(self, config: Dict[str, Any]) -> Any:
        """
        Eventually assert that condition becomes true (softer version of wait_until).

        Example:
        - step: assert_zone_eventually_online
          type: eventually
          condition: "context.get('zone_status') == 'online'"
          timeout: 60.0
        """
        condition_expr = config.get("condition", "")
        timeout = config.get("timeout", 30.0)
        interval = config.get("interval", 2.0)

        if not condition_expr:
            raise ValueError("eventually requires 'condition' parameter")

        try:
            await asyncio.wait_for(
                self._wait_for_condition(condition_expr, interval),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            # For eventually, we don't fail - just warn
            logger.warning(f"Condition '{condition_expr}' did not become true within {timeout}s")
            return False

    async def _wait_for_condition(self, condition_expr: str, interval: float) -> None:
        """Wait for condition to become true."""
        while True:
            if self._evaluate_condition(condition_expr):
                return
            await asyncio.sleep(interval)

    def _evaluate_condition(self, condition_expr: str) -> bool:
        """
        Evaluate a condition expression.

        Supports:
        - Simple Python expressions with context variables
        - Access to context dictionary
        - Basic operators and functions
        """
        try:
            # Create safe evaluation context
            context = self.variable_resolver.context
            eval_context = {
                'context': context,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'isinstance': isinstance,
                'any': any,
                'all': all,
                'sum': sum,
                'max': max,
                'min': min,
                'abs': abs,
                'True': True,
                'False': False,
                'None': None,
            }

            # Add context variables directly
            eval_context.update(context)

            # Evaluate expression
            result = eval(condition_expr, {"__builtins__": {}}, eval_context)
            return bool(result)

        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition_expr}': {e}")
            return False

    async def wait_for_condition(self, condition_func: Callable[[], Awaitable[bool]],
                                timeout: float = 30.0, interval: float = 1.0,
                                description: str = "condition") -> bool:
        """
        Generic wait for condition function.

        Args:
            condition_func: Async function that returns True when condition is met
            timeout: Maximum time to wait
            interval: Check interval
            description: Description for logging

        Returns:
            True if condition was met, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            if await condition_func():
                logger.debug(f"Condition '{description}' met after {asyncio.get_event_loop().time() - start_time:.1f}s")
                return True

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Condition '{description}' not met within {timeout}s")
                return False

            await asyncio.sleep(interval)

    async def eventually(self, condition_func: Callable[[], Awaitable[bool]],
                        timeout: float = 30.0, interval: float = 2.0,
                        description: str = "condition") -> bool:
        """
        Eventually wait for condition (non-failing version).

        Args:
            condition_func: Async function that returns True when condition is met
            timeout: Maximum time to wait
            interval: Check interval
            description: Description for logging

        Returns:
            True if condition was met, False if timeout (no exception raised)
        """
        try:
            return await asyncio.wait_for(
                self._wait_for_condition_func(condition_func, interval),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Condition '{description}' did not become true within {timeout}s")
            return False

    async def _wait_for_condition_func(self, condition_func: Callable[[], Awaitable[bool]], interval: float) -> bool:
        """Wait for condition function to return True."""
        while True:
            if await condition_func():
                return True
            await asyncio.sleep(interval)
