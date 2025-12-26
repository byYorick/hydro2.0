"""
Test suite management and CLI for E2E tests.
"""

import asyncio
import logging
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Import E2ERunner only when needed to avoid dependency issues

logger = logging.getLogger(__name__)


class TestSuite:
    """Manages test suites and provides CLI interface."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.runner: Optional[E2ERunner] = None

    async def run_scenario(self, scenario_path: str, **kwargs) -> bool:
        """
        Run a single scenario.

        Args:
            scenario_path: Path to scenario YAML file
            **kwargs: Additional runner configuration

        Returns:
            True if scenario passed
        """
        # Dynamic import to avoid dependency issues
        from .e2e_runner import E2ERunner

        # Create runner with merged config
        runner_config = {**self.config, **kwargs}
        self.runner = E2ERunner(runner_config)

        try:
            await self.runner.setup()
            success = await self.runner.run_scenario(scenario_path)
            return success
        finally:
            if self.runner:
                await self.runner.cleanup()

    async def run_scenarios(self, scenario_paths: List[str], **kwargs) -> Dict[str, bool]:
        """
        Run multiple scenarios.

        Args:
            scenario_paths: List of scenario paths
            **kwargs: Additional runner configuration

        Returns:
            Dict mapping scenario path to success status
        """
        results = {}

        for scenario_path in scenario_paths:
            logger.info(f"Running scenario: {scenario_path}")
            try:
                success = await self.run_scenario(scenario_path, **kwargs)
                results[scenario_path] = success
                status = "PASSED" if success else "FAILED"
                logger.info(f"Scenario {scenario_path}: {status}")
            except Exception as e:
                logger.error(f"Scenario {scenario_path} failed with exception: {e}")
                results[scenario_path] = False

        return results

    async def run_suite(self, suite_name: str, **kwargs) -> Dict[str, bool]:
        """
        Run a predefined test suite.

        Args:
            suite_name: Name of the suite (smoke, core, full, etc.)
            **kwargs: Additional runner configuration

        Returns:
            Dict mapping scenario path to success status
        """
        scenario_paths = self._get_suite_scenarios(suite_name)
        if not scenario_paths:
            raise ValueError(f"Unknown suite: {suite_name}")

        logger.info(f"Running suite '{suite_name}' with {len(scenario_paths)} scenarios")
        return await self.run_scenarios(scenario_paths, **kwargs)

    def _get_suite_scenarios(self, suite_name: str) -> List[str]:
        """Get scenarios for a suite."""
        base_path = Path(__file__).parent.parent / "scenarios"

        suites = {
            "smoke": [
                str(base_path / "core" / "E00_schema_smoke.yaml"),
                str(base_path / "core" / "E00_api_smoke.yaml"),
            ],
            "core": [
                str(base_path / "core" / "E00_schema_smoke.yaml"),
                str(base_path / "core" / "E00_api_smoke.yaml"),
                str(base_path / "core" / "E01_bootstrap.yaml"),
                str(base_path / "core" / "E02_auth_ws_api.yaml"),
            ],
            "commands": [
                str(base_path / "commands" / "E10_command_happy.yaml"),
                str(base_path / "commands" / "E11_command_failed.yaml"),
                str(base_path / "commands" / "E12_command_timeout.yaml"),
                str(base_path / "commands" / "E13_command_duplicate_response.yaml"),
                str(base_path / "commands" / "E14_command_response_before_sent.yaml"),
            ],
            "alerts": [
                str(base_path / "alerts" / "E20_error_to_alert_realtime.yaml"),
                str(base_path / "alerts" / "E21_alert_dedup_count.yaml"),
                str(base_path / "alerts" / "E22_unassigned_error_capture.yaml"),
                str(base_path / "alerts" / "E23_unassigned_attach_on_registry.yaml"),
                str(base_path / "alerts" / "E24_laravel_down_pending_alerts.yaml"),
                str(base_path / "alerts" / "E25_dlq_replay.yaml"),
            ],
            "infrastructure": [
                str(base_path / "infrastructure" / "E40_zone_readiness_fail.yaml"),
                str(base_path / "infrastructure" / "E41_zone_readiness_warn_start_anyway.yaml"),
                str(base_path / "infrastructure" / "E42_bindings_role_resolution.yaml"),
            ],
            "grow_cycle": [
                str(base_path / "grow_cycle" / "E50_create_cycle_planned.yaml"),
                str(base_path / "grow_cycle" / "E51_start_cycle_running.yaml"),
                str(base_path / "grow_cycle" / "E52_stage_progress_timeline.yaml"),
                str(base_path / "grow_cycle" / "E53_manual_advance_stage.yaml"),
                str(base_path / "grow_cycle" / "E54_pause_resume_harvest.yaml"),
            ],
            "automation_engine": [
                str(base_path / "automation_engine" / "E60_climate_control_happy.yaml"),
                str(base_path / "automation_engine" / "E61_fail_closed_corrections.yaml"),
                str(base_path / "automation_engine" / "E62_controller_fault_isolation.yaml"),
                str(base_path / "automation_engine" / "E63_backoff_on_errors.yaml"),
            ],
            "snapshot": [
                str(base_path / "snapshot" / "E30_snapshot_contains_last_event_id.yaml"),
                str(base_path / "snapshot" / "E31_reconnect_replay_gap.yaml"),
                str(base_path / "snapshot" / "E32_out_of_order_guard.yaml"),
            ],
            "chaos": [
                str(base_path / "chaos" / "E70_mqtt_down_recovery.yaml"),
                str(base_path / "chaos" / "E71_db_flaky.yaml"),
                str(base_path / "chaos" / "E72_ws_down_snapshot_recover.yaml"),
            ],
            "full": self._get_all_scenarios()
        }

        return suites.get(suite_name, [])

    def _get_all_scenarios(self) -> List[str]:
        """Get all available scenarios."""
        base_path = Path(__file__).parent.parent / "scenarios"
        scenarios = []

        # Scan all subdirectories for YAML files
        for pattern in ["**/*.yaml", "**/*.yml"]:
            for yaml_file in base_path.glob(pattern):
                if yaml_file.is_file():
                    scenarios.append(str(yaml_file))

        return sorted(scenarios)

    def discover_scenarios(self, paths: List[str] = None) -> List[str]:
        """
        Discover scenarios from files, directories, or suite names.

        Args:
            paths: List of files, directories, or suite names

        Returns:
            List of scenario file paths
        """
        if not paths:
            return self._get_suite_scenarios("smoke")

        scenarios = []
        base_path = Path(__file__).parent.parent / "scenarios"

        for path in paths:
            # Check if it's a predefined suite
            if path in ["smoke", "core", "commands", "alerts", "infrastructure",
                       "grow_cycle", "automation_engine", "snapshot", "chaos", "full"]:
                scenarios.extend(self._get_suite_scenarios(path))
                continue

            # Check if it's a direct file path
            if Path(path).is_absolute() or Path(path).exists():
                if Path(path).is_file() and path.endswith(('.yaml', '.yml')):
                    scenarios.append(path)
                elif Path(path).is_dir():
                    for yaml_file in Path(path).glob("**/*.yaml"):
                        scenarios.append(str(yaml_file))
                continue

            # Try relative to scenarios directory
            rel_path = base_path / path
            if rel_path.is_file() and rel_path.suffix in ['.yaml', '.yml']:
                scenarios.append(str(rel_path))
            elif rel_path.is_dir():
                for yaml_file in rel_path.glob("**/*.yaml"):
                    scenarios.append(str(yaml_file))
            else:
                # Try with .yaml extension
                yaml_path = base_path / f"{path}.yaml"
                if yaml_path.exists():
                    scenarios.append(str(yaml_path))

        return list(set(scenarios))  # Remove duplicates

    def filter_scenarios_by_tags(self, scenarios: List[str], include_tags: List[str] = None,
                                exclude_tags: List[str] = None) -> List[str]:
        """
        Filter scenarios by tags.

        Args:
            scenarios: List of scenario paths
            include_tags: Tags that must be present (supports 'and', 'or', 'not')
            exclude_tags: Tags that must NOT be present

        Returns:
            Filtered list of scenarios
        """
        if not include_tags and not exclude_tags:
            return scenarios

        filtered = []

        for scenario_path in scenarios:
            try:
                tags = self._get_scenario_tags(scenario_path)

                # Check exclude tags first
                if exclude_tags and any(tag in tags for tag in exclude_tags):
                    continue

                # Check include tags
                if include_tags:
                    if not self._matches_tag_filter(tags, include_tags):
                        continue

                filtered.append(scenario_path)

            except Exception as e:
                logger.warning(f"Failed to read tags from {scenario_path}: {e}")
                # If we can't read tags, include by default (fail-safe)
                if not exclude_tags:
                    filtered.append(scenario_path)

        return filtered

    def _get_scenario_tags(self, scenario_path: str) -> List[str]:
        """Extract tags from scenario file."""
        import yaml

        with open(scenario_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        tags = []

        # Tags in scenario metadata
        if 'tags' in data:
            if isinstance(data['tags'], list):
                tags.extend(data['tags'])
            elif isinstance(data['tags'], str):
                tags.append(data['tags'])

        # Infer tags from path
        path_parts = Path(scenario_path).parts
        if 'core' in path_parts:
            tags.append('core')
        if 'commands' in path_parts:
            tags.append('commands')
        if 'alerts' in path_parts:
            tags.append('alerts')
        if 'infrastructure' in path_parts:
            tags.append('infrastructure')
        if 'grow_cycle' in path_parts:
            tags.append('grow_cycle')
        if 'automation_engine' in path_parts:
            tags.append('automation_engine')
        if 'chaos' in path_parts:
            tags.append('chaos')

        # Infer tags from filename
        filename = Path(scenario_path).name
        if 'smoke' in filename.lower():
            tags.append('smoke')
        if 'bootstrap' in filename.lower():
            tags.append('bootstrap')
        if 'auth' in filename.lower():
            tags.append('auth')
        if 'api' in filename.lower():
            tags.append('api')
        if 'ws' in filename.lower() or 'websocket' in filename.lower():
            tags.append('websocket')
        if 'mqtt' in filename.lower():
            tags.append('mqtt')
        if 'db' in filename.lower() or 'database' in filename.lower():
            tags.append('database')

        return list(set(tags))  # Remove duplicates

    def _matches_tag_filter(self, scenario_tags: List[str], filter_tags: List[str]) -> bool:
        """Check if scenario tags match the filter expression."""
        # Simple OR logic for now - scenario matches if it has ANY of the filter tags
        return any(tag in scenario_tags for tag in filter_tags)

    def shard_scenarios(self, scenarios: List[str], shard_spec: str) -> List[str]:
        """
        Shard scenarios for parallel execution.

        Args:
            scenarios: List of scenario paths
            shard_spec: Shard specification like "1/3" (run first third)

        Returns:
            Subset of scenarios for this shard
        """
        try:
            shard_index, total_shards = map(int, shard_spec.split('/'))
            if shard_index < 1 or total_shards < 1 or shard_index > total_shards:
                raise ValueError(f"Invalid shard spec: {shard_spec}")

            # Calculate slice for this shard
            scenarios_per_shard = len(scenarios) // total_shards
            remainder = len(scenarios) % total_shards

            start_idx = (shard_index - 1) * scenarios_per_shard
            if shard_index <= remainder:
                start_idx += shard_index - 1
                end_idx = start_idx + scenarios_per_shard + 1
            else:
                start_idx += remainder
                end_idx = start_idx + scenarios_per_shard

            return scenarios[start_idx:end_idx]

        except (ValueError, ZeroDivisionError) as e:
            logger.error(f"Invalid shard specification '{shard_spec}': {e}")
            return scenarios

    @staticmethod
    def create_cli_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            description="E2E Test Runner - Modular YAML-based testing framework",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s smoke                           # Run smoke tests
  %(prog)s core/E01_bootstrap.yaml         # Run specific scenario
  %(prog)s --suite full --shard 1/3        # Run first third of full suite
  %(prog)s --tags api --repeat 3           # Run API tests 3 times
  %(prog)s --tags "slow or integration"    # Run scenarios with specific tags
            """
        )

        parser.add_argument(
            "scenarios",
            nargs="*",
            help="Scenario files, directories, or suite names to run"
        )

        parser.add_argument(
            "--suite", "-s",
            choices=["smoke", "core", "commands", "alerts", "infrastructure",
                    "grow_cycle", "automation_engine", "snapshot", "chaos", "full"],
            help="Run predefined test suite"
        )

        parser.add_argument(
            "--tags", "-t",
            action="append",
            help="Filter scenarios by tags (supports 'and', 'or', 'not' logic). Can be used multiple times."
        )

        parser.add_argument(
            "--exclude-tags", "-T",
            action="append",
            help="Exclude scenarios with these tags"
        )

        parser.add_argument(
            "--repeat", "-r",
            type=int,
            default=1,
            help="Repeat scenarios N times (default: 1)"
        )

        parser.add_argument(
            "--shard",
            type=str,
            help="Shard scenarios across parallel runs (format: 'N/M' where N is shard index, M is total shards)"
        )

        parser.add_argument(
            "--parallel", "-p",
            type=int,
            default=1,
            help="Run scenarios in parallel with N processes (default: 1)"
        )

        parser.add_argument(
            "--keep-up", "-k",
            action="store_true",
            help="Keep infrastructure running after tests complete"
        )

        parser.add_argument(
            "--dry-run", "-d",
            action="store_true",
            help="Show which scenarios would be run without executing them"
        )

        parser.add_argument(
            "--fail-fast", "-f",
            action="store_true",
            help="Stop execution on first failure"
        )

        parser.add_argument(
            "--report",
            type=str,
            choices=["junit", "json", "html", "all"],
            default="all",
            help="Generate test reports (default: all)"
        )

        parser.add_argument(
            "--output", "-o",
            type=str,
            help="Output directory for reports (default: reports/)"
        )

        parser.add_argument(
            "--config", "-c",
            type=str,
            help="Path to custom config file"
        )

        parser.add_argument(
            "--env",
            type=str,
            help="Environment name (development, staging, production)"
        )

        parser.add_argument(
            "--verbose", "-v",
            action="count",
            default=0,
            help="Increase verbosity (can be used multiple times: -v, -vv, -vvv)"
        )

        parser.add_argument(
            "--list",
            action="store_true",
            help="List available scenarios and suites"
        )

        parser.add_argument(
            "--list-tags",
            action="store_true",
            help="List all available tags in scenarios"
        )

        return parser

    async def run_from_cli(self, args: Optional[List[str]] = None) -> int:
        """
        Run tests from command line arguments.

        Args:
            args: Command line arguments (uses sys.argv if None)

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        parser = self.create_cli_parser()
        parsed_args = parser.parse_args(args or sys.argv[1:])

        # Setup logging
        if parsed_args.verbose >= 3:
            level = logging.DEBUG
        elif parsed_args.verbose >= 2:
            level = logging.INFO
        elif parsed_args.verbose >= 1:
            level = logging.WARNING
        else:
            level = logging.ERROR

        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        try:
            # Handle special commands
            if parsed_args.list:
                return await self._handle_list_command(parsed_args)
            elif parsed_args.list_tags:
                return await self._handle_list_tags_command(parsed_args)

            # Discover scenarios
            if parsed_args.suite:
                scenarios = self._get_suite_scenarios(parsed_args.suite)
            else:
                scenarios = self.discover_scenarios(parsed_args.scenarios or ["smoke"])

            # Apply tag filters
            if parsed_args.tags or parsed_args.exclude_tags:
                scenarios = self.filter_scenarios_by_tags(
                    scenarios,
                    parsed_args.tags,
                    parsed_args.exclude_tags
                )

            # Apply sharding
            if parsed_args.shard:
                scenarios = self.shard_scenarios(scenarios, parsed_args.shard)

            # Dry run
            if parsed_args.dry_run:
                self._print_dry_run_info(scenarios, parsed_args)
                return 0

            # Runner config
            runner_config = {}
            if parsed_args.keep_up:
                runner_config["keep_infra_up"] = True
            if parsed_args.env:
                runner_config["environment"] = parsed_args.env

            # Run scenarios
            all_passed = True
            total_run = 0
            total_passed = 0

            # Repeat execution
            for repeat in range(parsed_args.repeat):
                if parsed_args.repeat > 1:
                    logger.info(f"Repeat {repeat + 1}/{parsed_args.repeat}")

                # For now, sequential execution (parallel support can be added later)
                for scenario in scenarios:
                    if parsed_args.fail_fast and not all_passed:
                        break

                    success = await self.run_scenario(scenario, **runner_config)
                    total_run += 1
                    if success:
                        total_passed += 1
                    else:
                        all_passed = False

                    if parsed_args.fail_fast and not success:
                        break

            # Generate reports
            if parsed_args.report != "none":
                self._generate_reports(parsed_args, total_passed, total_run)

            # Summary
            logger.info(f"Results: {total_passed}/{total_run} scenarios passed")
            return 0 if all_passed else 1

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            if parsed_args.verbose >= 2:
                import traceback
                traceback.print_exc()
            return 1

    async def _handle_list_command(self, args) -> int:
        """Handle --list command."""
        print("Available test suites:")
        suites = ["smoke", "core", "commands", "alerts", "infrastructure",
                 "grow_cycle", "automation_engine", "snapshot", "chaos", "full"]
        for suite in suites:
            scenarios = self._get_suite_scenarios(suite)
            print(f"  {suite}: {len(scenarios)} scenarios")

        print("\nAll available scenarios:")
        all_scenarios = self._get_all_scenarios()
        for scenario in sorted(all_scenarios):
            rel_path = Path(scenario).relative_to(Path(__file__).parent.parent / "scenarios")
            print(f"  {rel_path}")
        return 0

    async def _handle_list_tags_command(self, args) -> int:
        """Handle --list-tags command."""
        print("Available tags:")
        all_scenarios = self._get_all_scenarios()
        all_tags = set()

        for scenario in all_scenarios:
            tags = self._get_scenario_tags(scenario)
            all_tags.update(tags)

        for tag in sorted(all_tags):
            print(f"  {tag}")
        return 0

    def _print_dry_run_info(self, scenarios: List[str], args) -> None:
        """Print dry run information."""
        print(f"Would run {len(scenarios)} scenarios:")
        for scenario in scenarios:
            rel_path = Path(scenario).relative_to(Path(__file__).parent.parent / "scenarios")
            tags = self._get_scenario_tags(scenario)
            print(f"  {rel_path} [tags: {', '.join(tags)}]")

        if args.repeat > 1:
            print(f"Each scenario would be repeated {args.repeat} times")

    def _generate_reports(self, args, passed: int, total: int) -> None:
        """Generate test reports."""
        output_dir = Path(args.output) if args.output else Path(__file__).parent.parent / "reports"

        # Create basic summary
        summary = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "timestamp": str(Path(__file__).parent.parent / "reports" / "summary.json").replace("summary.json", ""),
            "scenarios": []
        }

        with open(output_dir / "summary.json", 'w') as f:
            import json
            json.dump(summary, f, indent=2)

        logger.info(f"Reports generated in {output_dir}")


async def main():
    """Main CLI entry point."""
    suite = TestSuite()
    exit_code = await suite.run_from_cli()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
