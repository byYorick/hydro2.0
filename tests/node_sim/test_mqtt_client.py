from node_sim.mqtt_client import MqttClient


class _StubPahoClient:
    def __init__(self):
        self.will_args = None

    def will_set(self, topic, payload, qos, retain):
        self.will_args = (topic, payload, qos, retain)

    def username_pw_set(self, *args, **kwargs):
        pass

    def tls_set(self, *args, **kwargs):
        pass


def test_mqtt_client_sets_lwt(monkeypatch):
    stub = _StubPahoClient()

    def fake_client(*args, **kwargs):
        return stub

    monkeypatch.setattr("node_sim.mqtt_client.mqtt.Client", fake_client)

    client = MqttClient(client_id="node-sim-test")
    client.set_node_info(
        gh_uid="gh-1",
        zone_uid="zn-1",
        node_uid="nd-1",
        node_hw_id="hw-1",
        preconfig_mode=False,
    )

    client._create_client()

    assert stub.will_args == ("hydro/gh-1/zn-1/nd-1/lwt", "offline", 1, True)


def test_mqtt_client_skips_lwt_without_node_info(monkeypatch):
    stub = _StubPahoClient()

    def fake_client(*args, **kwargs):
        return stub

    monkeypatch.setattr("node_sim.mqtt_client.mqtt.Client", fake_client)

    client = MqttClient(client_id="node-sim-test")
    client._create_client()

    assert stub.will_args is None


def test_mqtt_client_sets_temp_lwt_in_preconfig(monkeypatch):
    stub = _StubPahoClient()

    def fake_client(*args, **kwargs):
        return stub

    monkeypatch.setattr("node_sim.mqtt_client.mqtt.Client", fake_client)

    client = MqttClient(client_id="node-sim-test")
    client.set_node_info(
        gh_uid="gh-temp",
        zone_uid="zn-temp",
        node_uid="nd-1",
        node_hw_id="hw-preconfig",
        preconfig_mode=True,
    )

    client._create_client()

    assert stub.will_args == ("hydro/gh-temp/zn-temp/hw-preconfig/lwt", "offline", 1, True)
