"""
Database step execution for E2E tests.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DatabaseStepExecutor:
    """Executes database-related steps in E2E scenarios."""

    def __init__(self, db_probe, variable_resolver):
        self.db_probe = db_probe
        self.variable_resolver = variable_resolver

    async def execute_db_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """
        Execute a database step.

        Args:
            step_type: Type of DB step
            config: Step configuration

        Returns:
            Query result or execution result
        """
        if step_type == "database_query":
            return await self._execute_database_query(config)
        elif step_type == "database_execute":
            return await self._execute_database_execute(config)
        elif step_type == "db.wait":
            return await self._execute_db_wait(config)
        elif step_type == "wait_for_telemetry":
            return await self._execute_wait_for_telemetry(config)
        else:
            raise ValueError(f"Unknown database step type: {step_type}")

    async def _execute_database_query(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute SELECT query."""
        query = config.get("query", "")
        params = config.get("params", {})

        # Resolve variables in query and params
        logger.info(f"Database executor _execute_database_query: resolving params {params}, context has zone_id: {'zone_id' in self.variable_resolver.context}")
        resolved_query = self.variable_resolver.resolve_variables(query)
        resolved_params = self.variable_resolver.resolve_variables(params)
        logger.info(f"Database executor _execute_database_query: resolved params {resolved_params}")

        # Validate critical params
        self.variable_resolver.validate_critical_params(resolved_params)

        return self.db_probe.query(resolved_query, resolved_params)

    async def _execute_database_execute(self, config: Dict[str, Any]) -> None:
        """Execute INSERT/UPDATE/DELETE query."""
        query = config.get("query", "")
        params = config.get("params", {})

        # Resolve variables in query and params
        resolved_query = self.variable_resolver.resolve_variables(query)
        resolved_params = self.variable_resolver.resolve_variables(params)

        # Validate critical params
        self.variable_resolver.validate_critical_params(resolved_params)

        self.db_probe.execute(resolved_query, resolved_params)

    async def _execute_db_wait(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Wait for database condition."""
        query = config.get("query", "")
        params = config.get("params", {})
        timeout = config.get("timeout", 10.0)
        expected_rows = config.get("expected_rows")

        # Resolve variables in query and params
        logger.info(f"Database executor _execute_db_wait: resolving params {params}, context has zone_id: {'zone_id' in self.variable_resolver.context}")
        resolved_query = self.variable_resolver.resolve_variables(query)
        resolved_params = self.variable_resolver.resolve_variables(params)
        logger.info(f"Database executor _execute_db_wait: resolved params {resolved_params}")

        # Validate critical params
        self.variable_resolver.validate_critical_params(resolved_params)

        return await self.db_probe.wait(
            query=resolved_query,
            params=resolved_params,
            timeout=timeout,
            expected_rows=expected_rows
        )

    async def _execute_wait_for_telemetry(self, config: Dict[str, Any]) -> bool:
        """Wait for telemetry to appear in database."""
        zone_id = config.get("zone_id")
        node_id = config.get("node_id")
        timeout = config.get("timeout", 15.0)

        if not zone_id or not node_id:
            raise ValueError("wait_for_telemetry requires zone_id and node_id")

        # Resolve variables
        resolved_zone_id = self.variable_resolver.resolve_variables(zone_id)
        resolved_node_id = self.variable_resolver.resolve_variables(node_id)

        # Wait for telemetry using the waiting executor
        from .waiting import WaitingStepExecutor
        waiting_executor = WaitingStepExecutor(self.variable_resolver)

        async def check_telemetry():
            result = self.db_probe.query(
                "SELECT COUNT(*) as count FROM telemetry_last WHERE zone_id = %s AND node_id = %s",
                (resolved_zone_id, resolved_node_id)
            )
            return result[0]["count"] > 0 if result else False

        return await waiting_executor.wait_for_condition(check_telemetry, timeout=timeout, description="telemetry in database")
