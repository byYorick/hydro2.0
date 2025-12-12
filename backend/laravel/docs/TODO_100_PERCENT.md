# TODO: Доработки до "идеала на 100%"

## Статус: В работе

---

## 1. Android-клиентская реализация

### 1.1. Хранение last_event_id локально
- **Статус:** Требует реализации
- **Приоритет:** P0
- **Описание:** Сохранять `last_event_id` для каждой зоны локально (SharedPreferences или локальная БД)
- **Документация:** См. `docs/ANDROID_CLIENT_IMPLEMENTATION.md` раздел 1

### 1.2. onResume: snapshot → events after_id → WS subscribe
- **Статус:** Требует реализации
- **Приоритет:** P0
- **Описание:** При возобновлении активности приложения:
  1. Получить snapshot зоны
  2. Выполнить catch-up пропущенных событий через Events API
  3. Подписаться на WebSocket
- **Документация:** См. `docs/ANDROID_CLIENT_IMPLEMENTATION.md` раздел 2

### 1.3. Reconciliation строго по event_id
- **Статус:** Требует реализации
- **Приоритет:** P0
- **Описание:** Использовать только `event_id` для reconciliation (НЕ использовать timestamp)
- **Документация:** См. `docs/ANDROID_CLIENT_IMPLEMENTATION.md` раздел 3

---

## 2. Оптимизация Telemetry в zone_events

### 2.1. Проблема
`NodeTelemetryUpdated` записывается в `zone_events` при каждом обновлении (каждые 3-5 секунд), что создает:
- ~12,000-28,800 событий в день для одной зоны
- Раздувание таблицы `zone_events`
- Медленные запросы catch-up

### 2.2. Решение: Вариант 1 - Фильтрация значимых изменений
- **Статус:** ✅ **Реализовано и интегрировано**
- **Приоритет:** P1
- **Описание:** Записывать телеметрию в ledger только при:
  - Значимых изменениях значения (больше порога)
  - Минимальном интервале между записями (60 секунд)
- **Реализация:** 
  - ✅ Создан `App\Services\TelemetryLedgerFilter`
  - ✅ Интегрирован в `NodeTelemetryUpdated::broadcasted()`
  - ✅ Написаны тесты (8 тестов, 11 проверок)
- **Документация:** См. `docs/TELEMETRY_LEDGER_OPTIMIZATION.md`

**Интеграция:**
```php
// В NodeTelemetryUpdated::broadcasted()
$filter = app(TelemetryLedgerFilter::class);
if (!$filter->shouldRecord($node->zone_id, $this->metricType, $this->value)) {
    return; // Не записываем
}
```

### 2.3. Решение: Вариант 2 - Исключить telemetry из ledger
- **Статус:** Требует решения
- **Приоритет:** P1
- **Описание:** Исключить телеметрию из ledger полностью. Телеметрия доступна через:
  - Snapshot (`latest_telemetry_per_channel`)
  - WebSocket stream (real-time)
  - Telemetry API (исторические данные)
- **Реализация:**
  ```php
  // В NodeTelemetryUpdated::broadcasted()
  // return; // Телеметрия исключена из ledger
  ```
- **Документация:** См. `docs/TELEMETRY_LEDGER_OPTIMIZATION.md`

**Рекомендация:** Вариант 2 (исключение) предпочтительнее для большинства случаев.

---

## 3. Выбор подхода для Telemetry

### Критерии выбора:

**Вариант 1 (Фильтрация) подходит, если:**
- ✅ Нужна история значимых изменений телеметрии в ledger
- ✅ Требуется catch-up для критических изменений телеметрии
- ✅ Можно настроить пороги для каждой метрики

**Вариант 2 (Исключение) подходит, если:**
- ✅ Телеметрия доступна через snapshot и WebSocket (уже так)
- ✅ Нужен компактный ledger для быстрого catch-up
- ✅ История телеметрии доступна через отдельный API

### Решение:
**Рекомендуем Вариант 2 (исключение)** - проще, быстрее, меньше сложности.

---

## 4. Чеклист реализации

### Android-клиент:
- [ ] Хранение `last_event_id` локально
- [ ] onResume: snapshot → catch-up → WS subscribe
- [ ] Reconciliation по `event_id`
- [ ] Обработка gap в событиях
- [ ] Unit и integration тесты

### Backend (Telemetry):
- [x] Решить: фильтрация или исключение ✅ **Выбрана фильтрация**
- [x] Если фильтрация: интегрировать `TelemetryLedgerFilter` ✅ **Интегрировано**
- [x] Написать тесты ✅ **8 тестов, все проходят**
- [ ] Архивировать существующие telemetry_updated события (опционально)
- [x] Обновить документацию ✅ **Документация создана**
- [ ] Мониторинг размера zone_events (требует настройки)

---

## 5. Метрики для мониторинга

После внедрения оптимизации:

1. **Размер zone_events**
   ```sql
   SELECT 
       type,
       COUNT(*) as count,
       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
   FROM zone_events
   WHERE created_at > NOW() - INTERVAL '1 day'
   GROUP BY type
   ORDER BY count DESC;
   ```

2. **Скорость catch-up**
   - Время ответа `/api/zones/{id}/events`
   - Размер gap в событиях

3. **Использование snapshot**
   - Частота запросов snapshot
   - Размер ответа snapshot

---

## 6. Приоритеты

### P0 (Критично):
- Android-клиент: хранение last_event_id
- Android-клиент: onResume flow
- Android-клиент: reconciliation по event_id

### P1 (Важно):
- Оптимизация telemetry в ledger
- Мониторинг метрик

### P2 (Желательно):
- Архивация старых telemetry_updated событий
- Дополнительные тесты

---

## 7. Ссылки на документацию

- **Android-клиент:** `docs/ANDROID_CLIENT_IMPLEMENTATION.md`
- **Telemetry оптимизация:** `docs/TELEMETRY_LEDGER_OPTIMIZATION.md`
- **Zone Event Ledger:** `doc_ai/...` (основная документация)

