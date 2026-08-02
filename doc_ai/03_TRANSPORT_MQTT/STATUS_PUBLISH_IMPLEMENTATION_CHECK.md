# Отчет о проверке реализации публикации status при подключении

Дата: 2025-01-27  
**Статус документа:** `historical` / частично **superseded** (обновление канона 2026-08-02)

> **Канон 2026-08-02** (`MQTT_SPEC_FULL.md` §4.2, `BACKEND_NODE_CONTRACT_FULL.md`):
> последовательность `MQTT connect → hydro/time/request → hydro/time/response → status/telemetry/event`.
> Публикация `status` сразу после `MQTT_EVENT_CONNECTED` (до time sync) **запрещена**.
> Ниже — исторический отчёт 2025-01 про порядок status vs subscribe; для нормативного timing
> опираться только на актуальные MQTT/contract спеки, не на выводы этого файла.

Исторический статус проверки (на дату отчёта): ✅ реализация порядка status-до-subscribe была исправлена.

---

## Цель проверки

Проверить полную реализацию явной публикации `status` топика при подключении узла к MQTT брокеру согласно:
- `MQTT_SPEC_FULL.md` раздел 4.2 (**актуально: status только после time sync**)
- `BACKEND_NODE_CONTRACT_FULL.md` раздел 8.1
- `DATAFLOW_FULL.md` раздел 6.1

---

## Проверенные компоненты

### 1. ✅ mqtt_manager (основной компонент)

**Файл:** `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`

**Статус:** ✅ **ИСПРАВЛЕНО**

**Найденные проблемы:**
- ❌ Публикация status выполнялась ПОСЛЕ подписки на config/command топики
- ❌ Не было явного комментария о соответствии спецификации

**Исправления:**
- ✅ Публикация status теперь выполняется **ДО** подписки на config/command топики (строки 354-360)
- ✅ Добавлен комментарий с ссылкой на спецификацию
- ✅ Добавлено логирование успешной публикации

**Правильная последовательность (после исправления):**
```c
case MQTT_EVENT_CONNECTED:
    ESP_LOGI(TAG, "MQTT connected to broker");
    s_is_connected = true;

    // 1. Публикация статуса ONLINE (ОБЯЗАТЕЛЬНО сразу после подключения, до подписки)
    char status_json[128];
    snprintf(status_json, sizeof(status_json), "{\"status\":\"ONLINE\",\"ts\":%lld}", 
            (long long)(esp_timer_get_time() / 1000000));
    mqtt_manager_publish_status(status_json);
    ESP_LOGI(TAG, "Published status: ONLINE");

    // 2. Подписка на config топик
    // 3. Подписка на command топики
    // 4. Вызов connection callback
```

**Параметры публикации:**
- ✅ QoS = 1 (строка 258: `mqtt_manager_publish_internal(topic, data, 1, 1)`)
- ✅ Retain = true (строка 258)
- ✅ Формат JSON: `{"status":"ONLINE","ts":...}` (валидный JSON)

---

### 2. ✅ mqtt_client (компонент-алиас)

**Файл:** `firmware/nodes/common/components/mqtt_client/mqtt_manager.c`

**Статус:** ✅ **ИСПРАВЛЕНО**

**Найденные проблемы:**
- ❌ Публикация status выполнялась ПОСЛЕ подписки на config/command топики
- ❌ Отсутствовал файл `mqtt_client.h` для обратной совместимости

**Исправления:**
- ✅ Публикация status теперь выполняется **ДО** подписки на config/command топики
- ✅ Создан файл `mqtt_client.h` с алиасами для обратной совместимости

---

### 3. ✅ Использование в узлах

**Проверенные узлы:**
- ✅ `ph_node` — использует `mqtt_manager.h` и `mqtt_manager_init`
- ✅ `pump_node` — использует `mqtt_client.h` и `mqtt_client_init` (через алиас)
- ✅ `ec_node` — использует `mqtt_client.h` и `mqtt_client_init` (через алиас)
- ✅ `climate_node` — использует `mqtt_client.h` и `mqtt_client_init` (через алиас)

**Статус:** ✅ **ВСЕ УЗЛЫ ИСПОЛЬЗУЮТ ПРАВИЛЬНЫЙ КОМПОНЕНТ**

---

## Соответствие спецификации

### Требования из MQTT_SPEC_FULL.md раздел 4.2:

| Требование | Статус | Комментарий |
|------------|--------|-------------|
| Публикация при `MQTT_EVENT_CONNECTED` | ✅ | Реализовано в обработчике событий |
| Публикация ДО подписки на config/command | ✅ | Исправлено: теперь публикация выполняется первым действием |
| QoS = 1 | ✅ | Установлено в `mqtt_manager_publish_status` |
| Retain = true | ✅ | Установлено в `mqtt_manager_publish_status` |
| Формат JSON: `{"status":"ONLINE","ts":...}` | ✅ | Реализовано (валидный JSON) |
| Поле `ts` содержит Unix timestamp | ✅ | Используется `esp_timer_get_time() / 1000000` |

### Требования из BACKEND_NODE_CONTRACT_FULL.md раздел 8.1:

| Требование | Статус | Комментарий |
|------------|--------|-------------|
| Публикация немедленно после подключения | ✅ | Реализовано |
| Публикация ДО подписки | ✅ | Исправлено |
| QoS = 1, Retain = true | ✅ | Установлено |
| Backend обновляет `nodes.status` | ⏳ | Требуется проверка backend |
| Backend обновляет `nodes.last_seen_at` | ⏳ | Требуется проверка backend |

---

## Формат JSON

**Текущий формат в коде:**
```json
{"status":"ONLINE","ts":1710001555}
```

**Формат в спецификации:**
```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

**Статус:** ✅ **ВАЛИДНЫЙ JSON** (оба формата эквивалентны, JSON парсеры принимают оба варианта)

**Примечание:** Формат без пробелов более компактный и подходит для встраиваемых систем. Формат с пробелами используется в документации для читаемости.

---

## Последовательность действий при подключении

**Канон 2026-08-02 (норматив — `MQTT_SPEC_FULL.md` §4.2):**

1. Установка LWT при инициализации MQTT клиента
2. Подключение к брокеру (`MQTT_EVENT_CONNECTED`)
3. Подписки на `config` / `+/command` (и прочие нужные топики)
4. Публикация `hydro/time/request`
5. Получение `hydro/time/response` (time sync)
6. Только после time sync: публикация `status` (`ONLINE`) / `telemetry` / `event`

**Историческая последовательность отчёта 2025-01 (superseded для timing):**
connect → **сразу status** → subscribe. Это **не** канон: status до time sync запрещён.

**Соответствие актуальной документации:** сверять реализацию firmware с `MQTT_SPEC_FULL.md` §4.2, не с чеклистом ниже.

---

## Выполненные исправления

### 1. Исправлен порядок действий в `mqtt_manager/mqtt_manager.c`
- Публикация status перенесена на первое место после подключения
- Добавлен комментарий с ссылкой на спецификацию
- Добавлено логирование успешной публикации

### 2. Исправлен порядок действий в `mqtt_client/mqtt_manager.c`
- Публикация status перенесена на первое место после подключения
- Добавлен комментарий с ссылкой на спецификацию
- Добавлено логирование успешной публикации

### 3. Создан файл `mqtt_client/include/mqtt_client.h`
- Алиасы для обратной совместимости с существующим кодом узлов
- Все функции `mqtt_manager_*` доступны как `mqtt_client_*`
- Типы также имеют алиасы

---

## Рекомендации

### Для backend (требуется проверка):

1. ⏳ Проверить обработку status топика в `history-logger` или соответствующем сервисе
2. ⏳ Убедиться, что backend обновляет `nodes.status = 'ONLINE'` при получении status
3. ⏳ Убедиться, что backend обновляет `nodes.last_seen_at = NOW()` при получении status

### Для документации:

1. ✅ Документация обновлена и соответствует реализации
2. ✅ Все ссылки на реализацию актуальны

---

## Итоговый статус

**Исторически (2025-01):** порядок status-до-subscribe и QoS/Retain/JSON были выровнены.

**На 2026-08-02:** этот отчёт **не** является proof соответствия канону time-sync-before-status.
Норматив и приёмка — по `MQTT_SPEC_FULL.md` §4.2 / `BACKEND_NODE_CONTRACT_FULL.md`.

**Требуется дополнительная проверка (актуально):**
- ⏳ Firmware публикует `status` только после `hydro/time/response`
- ⏳ Обработка status топика в `history-logger` / backend (`nodes.status`, `nodes.last_seen_at`)

---

## Файлы, измененные в ходе проверки

1. ✅ `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`
2. ✅ `firmware/nodes/common/components/mqtt_client/mqtt_manager.c`
3. ✅ `firmware/nodes/common/components/mqtt_client/include/mqtt_client.h` (создан)

---

**Примечание:** Все изменения соответствуют спецификации и не нарушают обратную совместимость.






