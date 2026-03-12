# Quick Start: MQTT Authentication Setup

## Для Development окружения

По умолчанию в development используется `allow_anonymous true` для упрощения разработки.

## Для Production окружения

### Шаг 1: Генерация файла паролей

**Вариант A: Используя Docker контейнер (рекомендуется для Windows)**

```bash
# Запустите временный контейнер с mosquitto
docker run --rm -it -v ${PWD}:/data eclipse-mosquitto:2 sh

# Внутри контейнера:
cd /data
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

exit
```

**Вариант B: Используя скрипт (Linux/macOS)**

```bash
cd backend/services/mqtt-bridge
chmod +x generate_passwords.sh
./generate_passwords.sh passwords
```

### Шаг 2: Включение аутентификации

После создания файла `passwords`, обновите `mosquitto.dev.conf`:

```conf
listener 1883
allow_anonymous false

password_file /mosquitto/config/passwords
acl_file /mosquitto/config/acl
```

### Шаг 3: Перезапуск

```bash
docker-compose -f backend/docker-compose.dev.yml restart mqtt
```

### Шаг 4: Проверка

```bash
# Проверка подключения
docker exec backend-mqtt-1 mosquitto_sub -h localhost -p 1883 -u automation_engine -P automation_pass -t 'test' -v
```

## Важно для Production

1. **Используйте сильные пароли** через переменные окружения
2. **Не коммитьте файл `passwords`** в git (добавлен в .gitignore)
3. **Регулярно меняйте пароли**
4. **Используйте TLS** для production (порт 8883)

