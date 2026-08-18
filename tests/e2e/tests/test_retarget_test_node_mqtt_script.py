#!/usr/bin/env python3
"""
Contract tests for tests/e2e/scripts/retarget_test_node_mqtt.sh
"""

import os
import re
import stat
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "retarget_test_node_mqtt.sh"


class TestRetargetTestNodeMqttScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SCRIPT_PATH.is_file():
            raise unittest.SkipTest(f"missing {SCRIPT_PATH}")
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_script_exists_and_is_executable_ish(self) -> None:
        self.assertTrue(SCRIPT_PATH.is_file(), msg=f"missing {SCRIPT_PATH}")
        self.assertTrue(
            self.script.startswith("#!/usr/bin/env bash"),
            msg="script must have a bash shebang",
        )
        mode = SCRIPT_PATH.stat().st_mode
        executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        self.assertTrue(
            executable or os.access(SCRIPT_PATH, os.X_OK),
            msg="script should be executable (chmod +x) or at least have execute bits",
        )
        self.assertIn("set -euo pipefail", self.script)

    def test_supports_e2e_and_dev_modes(self) -> None:
        self.assertIn("--e2e", self.script)
        self.assertIn("--dev", self.script)
        self.assertIn("TARGET_PORT=1884", self.script)
        self.assertIn("TARGET_PORT=1883", self.script)
        self.assertIn("--host", self.script)
        self.assertIn("--port", self.script)
        self.assertIn("--broker-port", self.script)

    def test_payload_is_mqtt_host_port_without_channels(self) -> None:
        self.assertIn('{"mqtt":{"host":"%s","port":%s}}', self.script)
        self.assertIn("nd-test-irrig-1/config", self.script)
        self.assertIn("${GH:-gh-test-1}", self.script)
        self.assertIn("${ZONE:-zn-test-1}", self.script)
        self.assertIn('NODE_UID="${NODE_UID:-nd-test-irrig-1}"', self.script)
        self.assertNotIn('"channels"', self.script)
        self.assertNotIn("'channels'", self.script)
        payload_line = next(
            line for line in self.script.splitlines() if line.strip().startswith("PAYLOAD=")
        )
        self.assertIn("mqtt", payload_line)
        self.assertNotIn("channels", payload_line)

    def test_does_not_default_node_host_to_mosquitto_or_localhost(self) -> None:
        self.assertIn("is_unusable_node_host", self.script)
        self.assertIn("|mosquitto|localhost|", self.script)
        self.assertIn("host.docker.internal", self.script)
        self.assertIn('LAB_DEFAULT_HOST="192.168.3.2"', self.script)
        self.assertIn("MQTT_EXTERNAL_HOST", self.script)
        self.assertIsNone(
            re.search(
                r': "\$\{(?:MQTT_EXTERNAL_HOST|NODE_HOST|HOST):=mosquitto\}"',
                self.script,
            )
        )
        self.assertNotIn('NODE_HOST="${MQTT_EXTERNAL_HOST:-mosquitto}"', self.script)
        self.assertNotIn('NODE_HOST="${MQTT_EXTERNAL_HOST:-localhost}"', self.script)
        self.assertNotIn('host":"mosquitto"', self.script)


if __name__ == "__main__":
    unittest.main()
