# MQTT Authentication Configuration

Документация по настройке аутентификации MQTT брокера.

## Обзор

MQTT брокер настроен с обязательной аутентификацией:
- `allow_anonymous false` - анонимные подключения запрещены
- `password_file` - файл с паролями пользователей
- `acl_file` - файл с правилами доступа к топикам

## Пользователи

### 1. python_service
- **Назначение:** Python сервисы (общий пользователь)
- **Пароль:** Настраивается через `MQTT_PYTHON_SERVICE_PASS`
- **Доступ:** Полный доступ к `hydro/#`

### 2. automation_engine
- **Назначение:** Automation Engine сервис
- **Пароль:** Настраивается через `MQTT_AUTOMATION_ENGINE_PASS`
- **Доступ:**
  - Чтение: `hydro/+/+/telemetry/#`, `hydro/+/+/status/#`
  - Запись: `hydro/+/+/commands/#`
  - Чтение/Запись: `hydro/+/+/events/#`

### 3. history_logger
- **Назначение:** History Logger сервис
- **Пароль:** Настраивается через `MQTT_HISTORY_LOGGER_PASS`
- **Доступ:**
  - Чтение: `hydro/+/+/telemetry/#`
  - Запись: `hydro/+/+/events/#`

### 4. scheduler
- **Назначение:** Scheduler сервис
- **Пароль:** Настраивается через `MQTT_SCHEDULER_PASS`
- **Доступ:**
  - Чтение: `hydro/+/+/status/#`, `hydro/+/+/telemetry/#`
  - Запись: `hydro/+/+/commands/#`

### 5. mqtt_bridge
- **Назначение:** MQTT Bridge сервис
- **Пароль:** Настраивается через `MQTT_MQTT_BRIDGE_PASS`
- **Доступ:** Полный доступ к `hydro/#`

### 6. esp32_node
- **Назначение:** ESP32 узлы
- **Пароль:** Настраивается через `MQTT_ESP32_NODE_PASS`
- **Доступ:**
  - Чтение/Запись: `hydro/+/+/esp32_node/#`
  - Запись: `hydro/+/+/+/status`
  - Чтение: `hydro/+/+/+/commands/#`

## Генерация паролей

### Автоматическая генерация

Используйте скрипт `generate_passwords.sh`:

```bash
cd backend/services/mqtt-bridge
./generate_passwords.sh passwords
```

Скрипт создаст файл `passwords` с хешами паролей для всех пользователей.

### Ручная генерация

```bash
# Создать новый файл паролей
mosquitto_passwd -c passwords python_service

# Добавить пользователя в существующий файл
mosquitto_passwd passwords automation_engine
```

### Использование переменных окружения

Для production используйте переменные окружения:

```bash
export MQTT_PYTHON_SERVICE_PASS="strong_password_here"
export MQTT_AUTOMATION_ENGINE_PASS="another_strong_password"
export MQTT_HISTORY_LOGGER_PASS="yet_another_password"
export MQTT_SCHEDULER_PASS="scheduler_password"
export MQTT_MQTT_BRIDGE_PASS="bridge_password"
export MQTT_ESP32_NODE_PASS="esp32_password"

cd backend/services/mqtt-bridge
./generate_passwords.sh passwords
```

## Конфигурация ACL

Файл `acl` определяет права доступа к топикам для каждого пользователя.

### Формат ACL

```
user <username>
topic [read|write|readwrite] <topic_pattern>
```

### Wildcards

- `+` - single level wildcard (один уровень)
  - Пример: `hydro/+/telemetry` соответствует `hydro/zone1/telemetry`, но не `hydro/zone1/node1/telemetry`
- `#` - multi-level wildcard (любое количество уровней)
  - Пример: `hydro/#` соответствует всем топикам, начинающимся с `hydro/`

### Примеры

```
# Полный доступ
user python_service
topic readwrite hydro/#

# Только чтение телеметрии
user history_logger
topic read hydro/+/+/telemetry/#

# Запись команд
user automation_engine
topic write hydro/+/+/commands/#
```

## Настройка в Docker Compose

### Development

В `docker-compose.dev.yml`:

```yaml
mqtt:
  volumes:
    - ./services/mqtt-bridge/mosquitto.dev.conf:/mosquitto/config/mosquitto.conf:ro
    - ./services/mqtt-bridge/passwords:/mosquitto/config/passwords:ro
    - ./services/mqtt-bridge/acl:/mosquitto/config/acl:ro
```

### Production

В `docker-compose.prod.yml`:

```yaml
mqtt:
  volumes:
    - ./services/mqtt-bridge/mosquitto.prod.conf:/mosquitto/config/mosquitto.conf:ro
    - ./services/mqtt-bridge/passwords:/mosquitto/config/passwords:ro
    - ./services/mqtt-bridge/acl:/mosquitto/config/acl:ro
```

## Настройка Python сервисов

Все Python сервисы должны использовать переменные окружения:

```yaml
environment:
  - MQTT_HOST=mqtt
  - MQTT_USER=automation_engine
  - MQTT_PASS=${MQTT_AUTOMATION_ENGINE_PASS:-change-me}
```

Сервисы автоматически используют эти credentials через `common/mqtt.py`.

## Настройка ESP32 узлов

ESP32 узлы получают MQTT credentials через конфигурацию:

```json
{
  "mqtt": {
    "host": "192.168.1.10",
    "port": 1883,
    "user": "esp32_node",
    "pass": "esp32_pass"
  }
}
```

Credentials передаются через OTA обновление или ручную настройку через setup portal.

## Проверка конфигурации

### Проверка паролей

```bash
# Проверить пользователя
mosquitto_passwd -c passwords test_user
# Введите пароль дважды

# Проверить существующий файл
cat passwords
```

### Проверка ACL

```bash
# Проверить синтаксис ACL
mosquitto -c mosquitto.dev.conf -v
```

### Тестирование подключения

```bash
# Подключиться с аутентификацией
mosquitto_sub -h localhost -p 1883 -u automation_engine -P automation_pass -t 'hydro/+/+/telemetry/#' -v

# Опубликовать сообщение
mosquitto_pub -h localhost -p 1883 -u automation_engine -P automation_pass -t 'hydro/test/zone1/telemetry/ph' -m '{"value": 6.5}'
```

## Безопасность

### Рекомендации для Production

1. **Используйте сильные пароли:**
   - Минимум 16 символов
   - Комбинация букв, цифр и символов
   - Уникальные пароли для каждого пользователя

2. **Регулярная ротация паролей:**
   - Меняйте пароли каждые 90 дней
   - Используйте секретный менеджер (HashiCorp Vault, AWS Secrets Manager)

3. **Ограничение доступа:**
   - Минимальные права доступа (принцип наименьших привилегий)
   - Регулярный аудит ACL файла

4. **Мониторинг:**
   - Логирование всех подключений
   - Алерты на подозрительную активность
   - Отслеживание неудачных попыток подключения

5. **TLS/SSL:**
   - В production используйте TLS (порт 8883)
   - Настройте сертификаты для всех клиентов

## Troubleshooting

### Ошибка: "Connection refused"

**Причина:** Неправильные credentials или пользователь не существует.

**Решение:**
1. Проверьте файл `passwords`
2. Убедитесь, что пользователь существует
3. Проверьте правильность пароля

### Ошибка: "Not authorized"

**Причина:** Пользователь не имеет прав доступа к топику.

**Решение:**
1. Проверьте файл `acl`
2. Убедитесь, что пользователь имеет права `read` или `write` для нужного топика
3. Проверьте синтаксис wildcards

### Ошибка: "File not found"

**Причина:** Файлы `passwords` или `acl` не смонтированы в контейнер.

**Решение:**
1. Проверьте volumes в `docker-compose.yml`
2. Убедитесь, что файлы существуют
3. Проверьте права доступа к файлам

## Миграция с allow_anonymous=true

Если вы обновляете существующую систему:

1. **Создайте файлы паролей и ACL:**
   ```bash
   cd backend/services/mqtt-bridge
   ./generate_passwords.sh passwords
   cp acl.example acl
   ```

2. **Обновите конфигурацию:**
   - Измените `allow_anonymous false` в `mosquitto.dev.conf`
   - Добавьте `password_file` и `acl_file`

3. **Обновите docker-compose:**
   - Добавьте volumes для `passwords` и `acl`
   - Добавьте `MQTT_USER` и `MQTT_PASS` для всех сервисов

4. **Перезапустите сервисы:**
   ```bash
   docker-compose -f backend/docker-compose.dev.yml restart mqtt
   docker-compose -f backend/docker-compose.dev.yml restart mqtt-bridge
   docker-compose -f backend/docker-compose.dev.yml restart automation-engine
   docker-compose -f backend/docker-compose.dev.yml restart history-logger
   docker-compose -f backend/docker-compose.dev.yml restart scheduler
   ```

5. **Проверьте подключения:**
   - Проверьте логи всех сервисов
   - Убедитесь, что нет ошибок аутентификации

