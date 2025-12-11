# Тестирование setup_portal компонента

## Описание

Компонент `setup_portal` предоставляет веб-интерфейс для первоначальной настройки ESP32 узлов через WiFi AP.

## Smoke-тест

### Требования

- Python 3.6+
- Библиотека `requests`: `pip install requests`
- Узел ESP32 в режиме setup (WiFi AP активен)

### Использование

#### Полный тест provisioning

```bash
python3 test_setup_portal.py \
  --ap-ssid "PH_SETUP_123456" \
  --wifi-ssid "MyHomeWiFi" \
  --wifi-password "mypassword123" \
  --mqtt-host "192.168.1.4" \
  --mqtt-port 1883
```

#### Только тестирование валидации payload

```bash
python3 test_setup_portal.py \
  --test-validation-only \
  --timeout 5
```

### Параметры

| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| `--ap-ssid` | SSID WiFi AP узла | Да (кроме `--test-validation-only`) |
| `--wifi-ssid` | SSID целевой WiFi сети | Да (кроме `--test-validation-only`) |
| `--wifi-password` | Пароль целевой WiFi сети | Да (кроме `--test-validation-only`) |
| `--mqtt-host` | IP адрес MQTT брокера | Да (кроме `--test-validation-only`) |
| `--mqtt-port` | Порт MQTT брокера (1-65535) | Да (кроме `--test-validation-only`) |
| `--ap-password` | Пароль WiFi AP (по умолчанию: `hydro2025`) | Нет |
| `--test-validation-only` | Только тестировать валидацию payload | Нет |
| `--timeout` | Таймаут запросов в секундах (по умолчанию: 10) | Нет |

### Формат provisioning payload

```json
{
  "ssid": "MyHomeWiFi",
  "password": "mypassword123",
  "mqtt_host": "192.168.1.4",
  "mqtt_port": 1883
}
```

### Валидация на узле

Узел проверяет:

1. **Обязательные поля:**
   - `ssid` (string)
   - `password` (string)
   - `mqtt_host` (string)
   - `mqtt_port` (number)

2. **Формат IP адреса:**
   - Должен быть в формате `xxx.xxx.xxx.xxx`
   - Каждый октет: 0-255

3. **Диапазон порта:**
   - Должен быть в диапазоне 1-65535

4. **Максимальная длина:**
   - `mqtt_host` не должен превышать `CONFIG_STORAGE_MAX_STRING_LEN` (128 символов)

### Ожидаемый ответ

При успешном provisioning:

```json
{
  "success": true
}
```

При ошибке валидации:

HTTP 400 Bad Request с текстовым сообщением об ошибке.

### Примеры использования

#### Тест с реальным узлом

1. Запустите узел в режиме setup (WiFi AP должен быть активен)
2. Подключитесь к WiFi AP узла (SSID: `PH_SETUP_123456`, пароль: `hydro2025`)
3. Запустите скрипт:

```bash
python3 test_setup_portal.py \
  --ap-ssid "PH_SETUP_123456" \
  --wifi-ssid "MyHomeWiFi" \
  --wifi-password "mypassword123" \
  --mqtt-host "192.168.1.4" \
  --mqtt-port 1883
```

4. Узел должен перезагрузиться и подключиться к указанному WiFi

#### Тест валидации (без реального provisioning)

```bash
python3 test_setup_portal.py \
  --test-validation-only
```

Этот режим проверяет только валидацию payload без реального сохранения конфигурации.

### Отладка

Если тест не проходит:

1. **Проверьте подключение к WiFi AP:**
   ```bash
   ping 192.168.4.1
   ```

2. **Проверьте, что узел в режиме setup:**
   - WiFi AP должен быть активен
   - SSID должен соответствовать формату `{TYPE}_SETUP_{PIN}`

3. **Проверьте логи узла:**
   - Узел должен логировать получение POST запроса
   - Проверьте наличие ошибок валидации

4. **Проверьте формат payload:**
   - Все поля должны быть правильного типа
   - IP адрес должен быть в формате `xxx.xxx.xxx.xxx`
   - Порт должен быть в диапазоне 1-65535

### Интеграция в CI/CD

Пример использования в CI/CD:

```yaml
- name: Test setup_portal
  run: |
    python3 firmware/nodes/common/components/setup_portal/test_setup_portal.py \
      --test-validation-only
```

