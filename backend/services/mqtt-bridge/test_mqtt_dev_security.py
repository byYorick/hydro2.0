"""Контракт dev-конфига Mosquitto: анонимный доступ выключен."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_dev_conf_disables_anonymous_and_enables_acl():
    text = (ROOT / "mosquitto.dev.conf").read_text(encoding="utf-8")
    assert "allow_anonymous false" in text
    assert "allow_anonymous true" not in text
    assert "password_file /mosquitto/config/passwords" in text
    assert "acl_file /mosquitto/config/acl" in text


def test_dev_compose_binds_broker_db_redis_to_loopback():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.dev.yml"
    text = compose.read_text(encoding="utf-8")
    assert '"${MQTT_BIND_ADDR:-127.0.0.1}:1883:1883"' in text
    assert '"${POSTGRES_BIND_ADDR:-127.0.0.1}:5432:5432"' in text
    assert '"${REDIS_BIND_ADDR:-127.0.0.1}:6379:6379"' in text
