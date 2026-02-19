# Frontend Audit — 2026-02-19
## Ручной аудит горячих точек (branch: AE2)

> Аудит выполнен вручную инструментами Grep (ripgrep в системе не установлен — `make audit` недоступен).
> Предыдущий автогенерированный отчёт: `artifacts/audit_report.md` (2025-12-30).

---

## P0 — Schema drift

**Статус: ✅ НЕ ОБНАРУЖЕНО**

Проверены обращения к `telemetry_samples` и агрегатным таблицам (`telemetry_agg_*`) в PHP-слое.
Все обращения изолированы в `history-logger` (Python) и миграциях Laravel.
Прямых raw SQL-запросов к `telemetry_samples` из контроллеров Laravel не найдено.

---

## P1 — Realtime

**Статус: ⚠️ Требует ревью**

| Категория | Количество |
|---|---|
| `Broadcasting::event()` / `->broadcast()` | 10 вызовов |
| `asyncio.create_task()` в Python-сервисах | 21 вызов |

Все realtime-события корректно проходят через Reverb (WebSocket).
Asyncio-задачи в automation-engine и scheduler — это ожидаемая архитектура.
Проблем не выявлено, но при масштабировании необходим мониторинг очереди Reverb.

---

## P1 — Retention (ДВОЙНОЙ МЕХАНИЗМ — требует решения)

**Статус: ⚠️ P1 — задокументировано, архитектурное решение откладывается**

### Hot telemetry (`telemetry_samples`)

| Механизм | Retention | Расписание |
|---|---|---|
| Laravel `telemetry:cleanup-raw --days=30` | **30 дней** | ежедневно в 02:00 |
| Python `telemetry-aggregator` (`RETENTION_SAMPLES_DAYS=90`) | 90 дней | фоновый сервис |

**Фактический retention = 30 дней** (Laravel агрессивнее и выигрывает).
Документ-политика `DATA_RETENTION_POLICY.md` обновлён: раздел 3.1 исправлен с "7–30 дней" → "30 дней".

### Aggregation (`telemetry_agg_*`)

| Механизм | Conflict strategy |
|---|---|
| Laravel `telemetry:aggregate` (каждые 15 мин) | `ON CONFLICT DO NOTHING` |
| Python `telemetry-aggregator` (непрерывно) | `ON CONFLICT DO UPDATE SET` |

**Дублирования данных нет** — конфликтная стратегия предотвращает коллизии.
Laravel-команда избыточна при работающем Python-сервисе, но безопасна.

### Рекомендация
Определить единственный owner retention и агрегации:
- Опция A: Python-сервис как единственный source, Laravel-команды — удалить
- Опция B: Laravel-команды как единственный source, Python-сервис — отключить cleanup/aggregate
- Опция C: Явно задокументировать дуальность и мониторить оба пути

Комментарии в `routes/console.php` добавлены для visibility.

---

## P2 — N+1 Queries (эвристика)

**Статус: ℹ️ Требует ручного ревью**

| Метрика | Значение |
|---|---|
| Вызовы Query::* в контроллерах (без eager load) | ~54 в 24 контроллерах |
| Eager load (`with(`, `load(`) | 49 |

Эвристика — не все 54 являются N+1. Необходимо ручное профилирование критических endpoint'ов
(dashboard, zone list, telemetry history).

---

## P2 — Queue Hotpath

**Статус: ℹ️ Информационно**

| Метрика | Значение |
|---|---|
| Job-классы (`implements ShouldQueue`) | 9 |
| `dispatch()` вызовов | 15 |

Очередь используется корректно. При росте нагрузки — настроить горизонтальный worker scaling.

---

## Frontend — TypeScript `as any`

**Статус: ✅ Частично исправлено**

| Состояние | `.vue` файлы | `as any` вхождения |
|---|---|---|
| До сессии | 33 файла | 71 вхождение |
| Исправлено в сессии | 3 файла | −19 вхождений |
| После сессии | ~30 файлов | ~52 вхождения |

### Исправлено в текущей сессии

| Файл | До | После | Метод |
|---|---|---|---|
| `Components/HeaderStatusBar.vue` | 7 | 0 | Добавлен `PageProps` interface, `usePage<PageProps>()` |
| `Components/ZoneComparisonModal.vue` | 6 | 0 | `getMetricValue()` → `number \| null`, typed zoneIds |
| `Pages/Devices/Add.vue` | 6 | 0 | `Device.pending_zone_id` добавлен в тип, typed error |

### Изменения в типах

| Файл | Изменение |
|---|---|
| `types/Device.ts` | Добавлено `pending_zone_id?: number \| null` |
| `types/Telemetry.ts` | Добавлены `avg?`, `min?`, `max?: number \| null` |

### Оставшиеся `as any` (~52 вхождений — приоритеты)

| Файл | Кол-во | Приоритет |
|---|---|---|
| `Pages/Dashboard/Dashboards/OperatorDashboard.vue` | ~4 | R3-4 |
| `Pages/Analytics/Index.vue` | ~4 | R3-4 |
| `Components/RelayConfigWizard.vue` | ~3 | R3-4 |
| `Components/ZoneCard.vue` | ~3 | R3-4 |
| `Pages/Auth/*.vue` | ~3 | R3-4 |
| Остальные файлы | ~35 | R3-4 |

### `console.log` в production

| Метрика | Значение |
|---|---|
| `console.log` в `.vue` файлах | 22 вхождения в 15 файлах |

Рекомендация: заменить на `console.warn`/`console.error` или удалить перед production.

---

## Typecheck после исправлений

```
npx tsc --noEmit → 0 ошибок
```

---

## Связанные изменения в сессии

### Рефакторинг (R2-5)
- `PumpCalibrationModal.vue`: 712 → 293 строк (−59%), логика вынесена в `usePumpCalibration.ts`
- `PlantCreateModal.vue`: уже декомпозирован (51 строк script, `usePlantCreateModal.ts` существует)

### Документация обновлена
- `doc_ai/07_FRONTEND/FRONTEND_REFACTORING_PLAN.md` — статус и метрики обновлены
- `doc_ai/05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md` — разделы 3.1, 3.2 обновлены
- `backend/laravel/routes/console.php` — предупреждения о двойном механизме добавлены

---

*Аудит выполнен: 2026-02-19 | Branch: AE2 | Следующий: автоматический `make audit` после установки ripgrep*
