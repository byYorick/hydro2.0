# TLS для MQTT (Mosquitto 8883)

Prod-брокер (`mosquitto.prod.conf`) по умолчанию слушает **1883 с паролем и ACL**, без анонимного доступа. Listener **8883** поднимает `mosquitto-entrypoint.sh`, когда в каталоге сертификатов есть `server.crt` и `server.key`.

## 1. Сертификат

Локальный самоподписанный (не для внешнего интернета):

```bash
cd backend/services/mqtt-bridge
MQTT_CERT_CN=mqtt.hydro.local MQTT_CERT_SAN=DNS:mqtt,IP:192.168.1.10 \
  ./generate_mqtt_certs.sh
```

Появятся `certs/ca.crt`, `certs/ca.key`, `certs/server.crt`, `certs/server.key`. Ключи не коммитить.

Публичный CA: положите те же имена файлов в `backend/services/mqtt-bridge/certs/`.

## 2. Брокер

`docker-compose.prod.yml` монтирует `certs/` в `/mosquitto/certs`. После появления `server.crt`/`server.key` перезапустите сервис `mqtt`: в логе будет `TLS listener 8883 enabled`. Порт 8883 публикуется наружу.

Пока клиенты не переведены, plaintext 1883 остаётся (`MQTT_PLAINTEXT_ENABLED=1`).

## 3. Python (history-logger, mqtt-bridge, automation-engine)

В `backend/.env.prod`:

```
MQTT_TLS=1
MQTT_PORT=8883
MQTT_CA_FILE=/etc/mqtt/certs/ca.crt
```

Каталог сертификатов смонтирован в контейнеры как `/etc/mqtt/certs`. `MQTT_TLS_INSECURE=1` отключает проверку hostname — только для отладки, не для production.

## 4. ESP32

1. Скопируйте `ca.crt` в `firmware/nodes/common/components/mqtt_manager/ca.pem`.
2. Пересоберите прошивку. Без этого файла `use_tls=true` клиент не подключается (fail-closed).
3. В NodeConfig узла: `mqtt.port=8883`, `mqtt.use_tls=true`, `mqtt.username=esp32_node`, пароль из `MQTT_ESP32_NODE_PASS`.
4. MQTT client id прошивки равен `node_uid`. ACL пускает узел только в `hydro/{gh}/{zone}/{свой node_uid}/#`, плюс `node_hello`, `time/*` и общий pre-bind `hydro/gh-temp/zn-temp/#`.

## 5. Выключить plaintext

Когда все клиенты на 8883:

```
MQTT_PLAINTEXT_ENABLED=0
```

Перезапуск `mqtt` уберёт listener 1883. Если сертификатов нет, процесс завершится с ошибкой — так и задумано.

## ACL сервисов

`readwrite hydro/#` оставлен только у `history_logger` (команды, config, телеметрия, time). `mqtt_bridge` читает status/lwt/heartbeat/telemetry. `automation_engine` и `python_service` топиков не имеют: AE ходит в history-logger по REST.
