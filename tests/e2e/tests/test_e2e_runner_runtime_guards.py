#!/usr/bin/env python3

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from runner.e2e_runner import E2ERunner  # noqa: E402


class TestE2ERunnerRuntimeGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = E2ERunner({"compose_file": str(E2E_ROOT / "docker-compose.e2e.yml")})

    def test_resolve_container_name_logs_and_falls_back_when_docker_ps_fails(self) -> None:
        with patch("runner.e2e_runner.subprocess.run", side_effect=RuntimeError("docker unavailable")):
            with self.assertLogs("runner.e2e_runner", level=logging.WARNING) as logs:
                name = self.runner._resolve_container_name("laravel")

        self.assertTrue(name.endswith("-laravel-1"))
        self.assertIn("using fallback name", "\n".join(logs.output))
