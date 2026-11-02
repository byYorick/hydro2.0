"""MQTT messages received between dispatch and assertion must remain available."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.mqtt_probe import MQTTProbe


class MQTTBufferTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_wait_reads_message_received_before_wait(self):
        probe = MQTTProbe()
        message = {'topic': 'hydro/gh/zn/nd/pump/command', 'payload': {'cmd_id': 'ci-1'}}
        probe._message_queue.append(message)
        result = await probe.wait_message(timeout=0.5, condition=lambda m: m['payload']['cmd_id'] == 'ci-1')
        self.assertIs(result, message)

    async def test_wait_does_not_return_consumed_message_twice(self):
        probe = MQTTProbe()
        probe._message_queue.append({'topic': 'old', 'payload': {}})
        self.assertIsNotNone(await probe.wait_message(timeout=0.5))
        probe._message_queue.append({'topic': 'new', 'payload': {}})
        self.assertEqual((await probe.wait_message(timeout=0.5))['topic'], 'new')

    async def test_clear_resets_consumption_cursor(self):
        probe = MQTTProbe()
        probe._message_queue.append({'topic': 'old', 'payload': {}})
        await probe.wait_message(timeout=0.5)
        probe.clear_messages()
        probe._message_queue.append({'topic': 'after-clear', 'payload': {}})
        self.assertEqual((await probe.wait_message(timeout=0.5))['topic'], 'after-clear')


if __name__ == '__main__':
    unittest.main()
