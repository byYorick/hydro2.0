import os
import uuid

import pytest


@pytest.fixture(autouse=True, scope="session")
def _unique_mqtt_client_id():
    original = os.environ.get("MQTT_CLIENT_ID")
    os.environ["MQTT_CLIENT_ID"] = f"hydro-core-test-{uuid.uuid4().hex[:8]}"
    yield
    if original is None:
        os.environ.pop("MQTT_CLIENT_ID", None)
    else:
        os.environ["MQTT_CLIENT_ID"] = original
