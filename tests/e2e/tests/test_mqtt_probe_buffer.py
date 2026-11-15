"""MQTT messages received between dispatch and assertion must remain available."""
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.mqtt_probe import MQTTProbe


class MQTTBufferTest(unittest.IsolatedAsyncioTestCase):
    def connected_probe(self):
        client = MagicMock()
        client.connect.side_effect = lambda *_: client.on_connect(client, None, {}, 0)
        probe = MQTTProbe()
        with patch('runner.mqtt_probe.mqtt.Client', return_value=client):
            probe.connect()
        return probe, client

    async def test_reconnect_restores_subscriptions_and_qos(self):
        probe, client = self.connected_probe()
        probe.subscribe('hydro/+/command', qos=2)
        client.on_disconnect(client, None, 7)
        self.assertFalse(probe.connected)
        client.on_connect(client, None, {}, 0)
        self.assertTrue(probe.connected)
        client.subscribe.assert_any_call('hydro/+/command', qos=2)
        self.assertEqual(probe._subscribed_topics, ['hydro/+/command'])

    async def test_rejected_connection_clears_ready_flag(self):
        probe, client = self.connected_probe()
        client.on_connect(client, None, {}, 5)
        self.assertFalse(probe.connected)

    async def test_publish_returns_receipt_for_broker_ack_verification(self):
        probe, client = self.connected_probe()
        receipt = probe.publish_json('hydro/response', {'status': 'DONE'})
        self.assertIs(receipt, client.publish.return_value)

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
