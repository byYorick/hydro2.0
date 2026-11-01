"""Контракт dev-конфига Mosquitto: анонимный доступ выключен."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_dev_conf_disables_anonymous_and_enables_acl():
    text = (ROOT / "mosquitto.dev.conf").read_text(encoding="utf-8")
    assert "allow_anonymous false" in text
    assert "allow_anonymous true" not in text
    assert "password_file /mosquitto/config/passwords" in text
    assert "acl_file /mosquitto/config/acl" in text


def test_acl_allows_time_sync_and_node_config_publish():
    """history-logger публикует time/response и NodeConfig; узел пишет time/request."""
    text = (ROOT / "acl").read_text(encoding="utf-8")
    history = _acl_user_block(text, "history_logger")
    node = _acl_user_block(text, "esp32_node")
    # SEC-02 объединяет права history-logger: он остаётся единственным
    # publisher команд/config и читателем всех входящих сообщений.
    assert "topic readwrite hydro/#" in history
    assert "topic write hydro/time/request" in node
    assert "topic read hydro/time/response" in node
    assert "pattern read hydro/+/+/%c/config" in text
    assert "pattern read hydro/+/+/%c/+/command" in text
    assert "topic read hydro/+/+/+/config" not in node
    assert "topic read hydro/+/+/+/+/command" not in node
    assert "topic write hydro/+/+/+/config" not in node
    assert "topic write hydro/+/+/+/+/command" not in node


def _acl_user_block(text: str, user: str) -> str:
    marker = f"user {user}\n"
    start = text.find(marker)
    assert start >= 0, user
    rest = text[start + len(marker):]
    next_user = rest.find("\nuser ")
    return rest if next_user < 0 else rest[:next_user]


def test_dev_compose_binds_broker_db_redis_to_loopback():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.dev.yml"
    text = compose.read_text(encoding="utf-8")
    assert '"${MQTT_BIND_ADDR:-127.0.0.1}:1883:1883"' in text
    assert '"${POSTGRES_BIND_ADDR:-127.0.0.1}:5432:5432"' in text
    assert '"${REDIS_BIND_ADDR:-127.0.0.1}:6379:6379"' in text
