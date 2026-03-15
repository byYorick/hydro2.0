#!/usr/bin/env python3
"""
Contract tests for test_node command latency profiles.
"""

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

TEST_NODE_APP = (
    REPO_ROOT / "firmware" / "test_node" / "main" / "test_node_app.c"
)
README_PATH = (
    REPO_ROOT / "firmware" / "test_node" / "README.md"
)
SPEC_PATH = (
    REPO_ROOT
    / "doc_ai"
    / "02_HARDWARE_FIRMWARE"
    / "TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md"
)


class TestTestNodeLatencyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TEST_NODE_APP.read_text(encoding="utf-8")
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.spec = SPEC_PATH.read_text(encoding="utf-8")

    def test_control_latency_constants_are_short(self) -> None:
        min_match = re.search(r"#define CONTROL_DELAY_MIN_MS (\d+)", self.source)
        max_match = re.search(r"#define CONTROL_DELAY_MAX_MS (\d+)", self.source)
        self.assertIsNotNone(min_match)
        self.assertIsNotNone(max_match)
        self.assertLessEqual(int(min_match.group(1)), 150)
        self.assertLessEqual(int(max_match.group(1)), 300)

    def test_non_transient_actuator_path_uses_control_delay_profile(self) -> None:
        self.assertIn("kind == COMMAND_KIND_ACTUATOR && (!job || !is_transient_command(job))", self.source)
        self.assertIn("random_range_ms(CONTROL_DELAY_MIN_MS, CONTROL_DELAY_MAX_MS)", self.source)

    def test_state_barrier_waits_for_quiet_window_before_snapshot(self) -> None:
        self.assertIn("static volatile bool s_command_worker_busy = false;", self.source)
        self.assertIn("static volatile int64_t s_last_non_state_command_rx_ms = 0;", self.source)
        self.assertIn("#define STATE_QUERY_BARRIER_QUIET_MS 1500", self.source)
        self.assertIn("quiet_since_ms < barrier_started_ms", self.source)
        self.assertIn("(now_ms - quiet_since_ms) >= STATE_QUERY_BARRIER_QUIET_MS", self.source)
        self.assertIn("uxQueueMessagesWaiting(s_command_queue) == 0", self.source)
        self.assertIn("&& !s_command_worker_busy", self.source)
        self.assertIn("s_last_non_state_command_rx_ms = get_uptime_ms_precise();", self.source)
        self.assertIn("xQueueSendToFront(s_command_queue, &job, 0)", self.source)
        self.assertIn("if (queue_send_status != pdTRUE && s_command_queue)", self.source)

    def test_readme_documents_control_latency_range(self) -> None:
        self.assertIn("короткие control-latency задержки `120..260 ms`", self.readme)
        self.assertIn("quiet-window `1500 ms`", self.readme)
        self.assertIn("раньше actuator-команд из других MQTT topic", self.readme)
        self.assertIn("недоступна или переполнена", self.readme)

    def test_prod_readiness_spec_documents_control_latency_range(self) -> None:
        self.assertIn("non-transient actuator control path", self.spec)
        self.assertIn("`120..260 ms`", self.spec)
        self.assertIn("quiet-window `1500 ms`", self.spec)
        self.assertIn("causally-correct `IRR_STATE_SNAPSHOT`", self.spec)
        self.assertIn("недоступности или переполнении", self.spec)


if __name__ == "__main__":
    unittest.main()
