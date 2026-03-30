# Changelog - Python Services

## 2026-03-30 — Планировщик только в Laravel

- Удалён отдельный Python-сервис `backend/services/scheduler` из боевого стека и supervisor.
- Расписания и wake-up: **Laravel** (`automation:dispatch-schedules`, intents) → `POST /zones/{id}/start-cycle` → automation-engine.
- Legacy `POST /scheduler/command` и HTTP task transport к Python-планировщику не используются.

## 2025-12-11 - Рефакторинг на REST API

### Архитектурные изменения

**Централизация публикации команд:**
- `history-logger` теперь **единственная точка публикации команд в MQTT**
- `automation-engine` публикует команды через `history-logger` REST API
- *(исторически)* отдельный Python scheduler ходил в AE/HL; **с 2026-03** dispatch в Laravel — см. запись выше

**Новые REST API endpoints:**

**History-Logger (порт 9300):**
- `POST /commands` - универсальный endpoint для команд
- `POST /zones/{zone_id}/commands` - команды для зоны
- `POST /nodes/{node_uid}/commands` - команды для ноды

**Automation-Engine (порт 9405):**
- `GET /health` - health check

### Улучшения

- ✅ Централизованное логирование всех команд
- ✅ Единая точка мониторинга команд
- ✅ Улучшенная безопасность (MQTT ACL обновлены)
- ✅ Полное покрытие тестами (42 теста, 100% успешность)

### Тестирование

- ✅ 20 тестов для automation-engine (CommandBus + REST API)
- ✅ 13 тестов для history-logger (REST API endpoints)

### Документация

- ✅ Обновлен `PYTHON_SERVICES_ARCH.md` с новой архитектурой
- ✅ Обновлены README файлы всех сервисов
- ✅ Удалены устаревшие отчеты

---

## 2025-11-22 - Оптимизация automation-engine

### Улучшения производительности

- ✅ Параллельная обработка зон (до 5 одновременно)
- ✅ Batch запросы к БД (снижение нагрузки на 40-50%)
- ✅ Адаптивная конкурентность с автоматическим расчетом
- ✅ Оптимизированные SQL запросы с CTE

### Улучшения надежности

- ✅ Централизованная обработка ошибок
- ✅ Retry механизм для критических операций
- ✅ Детальная информация об ошибках по зонам
- ✅ Метрики ошибок с детализацией

### Рефакторинг

- ✅ Выделение Correction Controller (убрано 200+ строк дублирования)
- ✅ Создание слоя репозиториев
- ✅ Создание сервисного слоя
- ✅ 72+ тестов покрывают основные компоненты

---

## 2025-11-01 - Batch processing оптимизации

### History-Logger улучшения

- ✅ Кеш `uid→id` с TTL refresh (60 секунд)
- ✅ Batch resolve недостающих UID
- ✅ Batch insert для `telemetry_samples`
- ✅ Batch upsert для `telemetry_last`
- ✅ Backpressure при >95% заполнения очереди
- ✅ Метрики и алерты на overflow

### Redis Queue

- ✅ Буферизация телеметрии в Redis
- ✅ Автоматический flush при достижении размера батча
- ✅ Graceful shutdown с обработкой оставшихся элементов

