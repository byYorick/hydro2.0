"""Exercise the shipped broker entrypoint, auth, ACL and TLS in a real container."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/services/mqtt-bridge"


class BrokerRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.directory.chmod(0o755)
        for name in ("acl", "mosquitto.dev.conf", "mosquitto-entrypoint.sh"):
            shutil.copyfile(SOURCE / name, cls.directory / name)
            (cls.directory / name).chmod(0o644)
        cls.name = "hydro-ci-mqtt-" + uuid.uuid4().hex[:10]
        cls.addClassCleanup(cls.temp.cleanup)
        cls.addClassCleanup(lambda: subprocess.run(
            ["docker", "rm", "-fv", cls.name], capture_output=True, check=False))
        subprocess.run(["sh", str(SOURCE / "generate_mqtt_certs.sh"),
                        str(cls.directory / "certs")], check=True, capture_output=True)
        subprocess.run([
            "docker", "run", "-d", "--name", cls.name,
            "-e", "MQTT_PLAINTEXT_ENABLED=0",
            "-v", f"{cls.directory}/acl:/mosquitto/config/acl:ro",
            "-v", f"{cls.directory}/mosquitto.dev.conf:/mosquitto/config/mosquitto.conf:ro",
            "-v", f"{cls.directory}/mosquitto-entrypoint.sh:/review-entrypoint.sh:ro",
            "-v", f"{cls.directory}/certs:/mosquitto/certs:ro",
            "--entrypoint", "sh", os.getenv("MQTT_TEST_IMAGE", "eclipse-mosquitto:2"),
            "/review-entrypoint.sh",
        ], check=True, capture_output=True)
        for _ in range(60):
            result = cls.publish("history_logger", "hl-ready", "hydro/test")
            if result.returncode == 0 and "Error" not in result.stderr:
                return
            time.sleep(0.5)
        logs = subprocess.run(["docker", "logs", cls.name], capture_output=True, text=True)
        raise AssertionError("Broker did not become ready: " + logs.stdout + logs.stderr)

    @classmethod
    def publish(cls, user, client_id, topic, *, tls=True, ca="/mosquitto/certs/ca.crt"):
        command = ["docker", "exec", cls.name, "mosquitto_pub", "-h", "localhost",
                   "-p", "8883" if tls else "1883", "-V", "mqttv5", "-q", "1",
                   "-i", client_id, "-t", topic, "-m", "ci-runtime-probe"]
        if tls:
            command += ["--cafile", ca]
        if user:
            passwords = {"history_logger": "logger_pass", "esp32_node": "esp32_pass"}
            command += ["-u", user, "-P", passwords[user]]
        return subprocess.run(command, capture_output=True, text=True, timeout=8)

    def assert_allowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Not authorized", result.stderr)

    def assert_denied(self, result):
        self.assertTrue(result.returncode != 0 or "Not authorized" in result.stderr, result)

    def test_own_telemetry_and_history_logger_commands(self):
        self.assert_allowed(self.publish("esp32_node", "nd-ci", "hydro/gh/zn/nd-ci/ph/telemetry"))
        self.assert_allowed(self.publish("history_logger", "hl-ci", "hydro/gh/zn/nd-ci/ph/command"))

    def test_anonymous_other_node_and_command_writes_denied(self):
        self.assert_denied(self.publish(None, "anonymous-ci", "hydro/test"))
        for topic in ("hydro/gh/zn/other/ph/telemetry", "hydro/gh/zn/nd-ci/ph/command",
                      "hydro/gh/zn/nd-ci/config", "hydro/gh-temp/zn-temp/nd-ci/config"):
            with self.subTest(topic=topic):
                self.assert_denied(self.publish("esp32_node", "nd-ci", topic))

    def test_plaintext_listener_is_disabled(self):
        self.assertNotEqual(self.publish("history_logger", "hl-plain", "hydro/test", tls=False).returncode, 0)

    def test_untrusted_certificate_is_rejected(self):
        self.assertNotEqual(self.publish("history_logger", "hl-bad-ca", "hydro/test",
                                        ca="/etc/ssl/certs/ca-certificates.crt").returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
