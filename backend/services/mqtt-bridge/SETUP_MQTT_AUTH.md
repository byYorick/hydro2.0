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
./generate_passwords.sh passwords
```

### Вариант B: Ручная генерация

```bash
cd backend/services/mqtt-bridge

# Создайте файл паролей
mosquitto_passwd -c passwords python_service
# Введите пароль: python_service_pass

mosquitto_passwd passwords automation_engine
# Введите пароль: automation_pass

mosquitto_passwd passwords history_logger
# Введите пароль: logger_pass

mosquitto_passwd passwords scheduler
# Введите пароль: scheduler_pass

mosquitto_passwd passwords mqtt_bridge
# Введите пароль: bridge_pass

mosquitto_passwd passwords esp32_node
# Введите пароль: esp32_pass
```

## Шаг 2: Проверка файлов

Убедитесь, что файлы существуют:

```bash
ls -la backend/services/mqtt-bridge/passwords
ls -la backend/services/mqtt-bridge/acl
```

## Шаг 3: Перезапуск MQTT брокера

```bash
docker-compose -f backend/docker-compose.dev.yml restart mqtt
```

## Шаг 4: Проверка подключения

```bash
# Проверка подключения с аутентификацией
docker exec backend-mqtt-1 mosquitto_sub -h localhost -p 1883 -u automation_engine -P automation_pass -t 'hydro/+/+/telemetry/#' -v
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

