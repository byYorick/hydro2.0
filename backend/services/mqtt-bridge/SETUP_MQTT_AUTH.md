# Quick Setup: MQTT Authentication

Быстрая инструкция по настройке MQTT аутентификации.

## Шаг 1: Генерация файла паролей

### Вариант A: Использование скрипта (рекомендуется)

```bash
cd backend/services/mqtt-bridge

# Установите mosquitto-clients (если еще не установлен)
# Ubuntu/Debian:
sudo apt-get install mosquitto-clients

# macOS:
brew install mosquitto

# Сгенерируйте файл паролей
chmod +x generate_passwords.sh
./generate_passwords.sh passwords.txt
```

### Вариант B: Ручная генерация

```bash
cd backend/services/mqtt-bridge

# Создайте файл паролей
mosquitto_passwd -c passwords.txt python_service
# Пароль: MQTT_PYTHON_SERVICE_PASS из backend/.env

mosquitto_passwd passwords.txt automation_engine
# Пароль: MQTT_AUTOMATION_ENGINE_PASS из backend/.env

mosquitto_passwd passwords.txt history_logger
# Пароль: MQTT_HISTORY_LOGGER_PASS из backend/.env

mosquitto_passwd passwords.txt mqtt_bridge
# Пароль: MQTT_MQTT_BRIDGE_PASS из backend/.env

mosquitto_passwd passwords.txt esp32_node
# Пароль: значение MQTT_ESP32_NODE_PASS из backend/.env (make ensure-dev-secrets)
```

## Шаг 2: Проверка файлов

Убедитесь, что файлы существуют:

```bash
ls -la backend/services/mqtt-bridge/passwords.txt
ls -la backend/services/mqtt-bridge/acl
```

## Шаг 3: Перезапуск MQTT брокера

```bash
docker-compose -f backend/docker-compose.dev.yml restart mqtt
```

## Шаг 4: Проверка подключения

```bash
# Проверка подключения с аутентификацией
docker exec backend-mqtt-1 mosquitto_sub -h localhost -p 1883 -u automation_engine -P "$MQTT_AUTOMATION_ENGINE_PASS" -t 'hydro/+/+/telemetry/#' -v
```

## Troubleshooting

Если возникают ошибки:

1. **Проверьте файлы:**
   ```bash
   docker exec backend-mqtt-1 cat /mosquitto/config/mosquitto.conf
   docker exec backend-mqtt-1 ls -la /mosquitto/config/
   ```

2. **Проверьте логи:**
   ```bash
   docker logs backend-mqtt-1
   ```

3. **Проверьте подключение сервисов:**
   ```bash
   docker logs backend-automation-engine-1 | grep -i mqtt
   docker logs backend-history-logger-1 | grep -i mqtt
   ```
