# MOBILE_AR_CHARTER.md
# Паспорт pipeline: мобильный оффлайн + AR-overlay для оператора

**Статус:** 🟡 CHARTER (nice-to-have, после основного функционала)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/MOBILE_AR_CHARTER.md`
**Связанные:** `mobile/`, `EXPLAINABILITY_UX_CHARTER.md`, `VISION_PIPELINE.md`

---

## 1. Назначение

Оператор физически ходит по теплице. Его задача — быстро понять, что не
так в конкретной зоне, и принять решение. Сейчас для этого нужно достать
телефон → открыть приложение → найти нужную зону по списку → листать карточки.
AR-overlay сокращает этот путь до «навёл камеру → увидел».

## 2. Цели

- Offline-first: приложение работает без связи, синхронизируется при
  появлении сети.
- AR-overlay: наведение камеры телефона на зону → поверх реальной картинки
  появляются ключевые метрики, активные alert'ы, последние advisory.
- QR-коды на зонах/узлах для быстрой идентификации без GPS.
- Голосовой ввод инспекций (операторам удобнее, руки заняты).
- Photo inspection flow: фото растения/листа → на сервер → анализ → ответ
  на телефоне через N секунд.

## 3. Ключевые дизайн-решения

1. **React Native / Flutter** — есть mobile/ в репо, уважаем выбор.
2. **ARCore/ARKit** не используем (тяжело, требует DGPS/глубинную камеру).
   Вместо — **QR-code identification** + простая отрисовка сверху
   обычной камеры.
3. **SQLite как offline-кэш**: все критичные данные зоны (последние 24ч
   метрики, активные alert'ы, config) кэшируются.
4. **Conflict-free writes**: offline-действия оператора (ack, feedback, note)
   пишутся с client_id + timestamp, на сервере мержатся.
5. **Photo → async analysis**: телефон загружает на S3 через pre-signed URL,
   когда есть сеть; получает уведомление через push при готовности.

## 4. Ключевые UI-флоу

### 4.1. AR zone overlay

- QR-код на табличке зоны → сканирование
- Показывает: zone name, health indicator (🟢/🟡/🔴), top 3 metrics (pH, EC, T),
  open alerts count, 1-tap до full zone page

### 4.2. Plant inspection

- Сфотографировать растение с листа/плода → send
- На сервере (VISION pipeline) → ответ через 5-10 сек push
- Оператор видит: «возможно Ca-дефицит (tip-burn score 0.62)» + рекомендация

### 4.3. Trap inspection (для IPM)

- Сфото клейкой ловушки → автоподсчёт → вернуть приложение с числами
- Оператор подтверждает / корректирует → feedback в модель

### 4.4. Voice field notes

- Кнопка hold-to-talk → распознавание → запись в `zone_events` или
  `vision_ground_truth`

## 5. Структура данных

Большинство таблиц уже существуют (`zone_events`, `vision_ground_truth`,
`alerts`). Добавляется:

```sql
CREATE TABLE zone_qr_codes (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  code_text varchar(64) NOT NULL UNIQUE,
  printed_at timestamptz,
  replaced_at timestamptz
);

CREATE TABLE mobile_field_inspections (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  plant_id bigint REFERENCES plants(id),
  operator_id bigint NOT NULL REFERENCES users(id),
  inspected_at timestamptz NOT NULL,
  submitted_at timestamptz NOT NULL,       -- когда загрузилось (может отличаться — offline)
  client_id varchar(64),                   -- UUID с клиента для idempotency
  mode varchar(16) NOT NULL,               -- 'visual'|'voice'|'photo'|'ar_overlay'
  payload jsonb NOT NULL,                  -- все собранные данные
  image_ids bigint[],                      -- ссылки на plant_images
  location_accuracy_m double precision,
  device_info jsonb
);

CREATE TABLE mobile_offline_queue_stats (
  device_id varchar(64) PRIMARY KEY,
  user_id bigint REFERENCES users(id),
  queue_size integer,
  oldest_queued_at timestamptz,
  last_sync_at timestamptz,
  fw_version varchar(32)
);
```

## 6. Backend API

Новые эндпоинты:
- `POST /v1/mobile/photo-analysis` (async, returns task_id)
- `GET /v1/mobile/zone-summary/{zone_id}` (минифицированный JSON для AR)
- `POST /v1/mobile/inspection` (offline-safe)
- `POST /v1/mobile/voice-note` (upload + speech-to-text)

## 7. Фазы

| Phase | Задача | DoD |
|---|---|---|
| MO0 | QR-код генератор + печать | Каждая зона имеет QR |
| MO1 | Mobile app zone overview | Открывается от QR |
| MO2 | Offline cache + sync | Работает без сети на 24+ часов |
| MO3 | Photo inspection flow | E2E: фото → ответ |
| MO4 | AR overlay базовый | Наведение → метрики над QR |
| MO5 | Voice notes | Распознавание пишет в `zone_events` |
| MO6 | Trap inspection integration | Photo traps из IPM |

## 8. Интеграция

- **VISION_PIPELINE** — mobile-загрузка фото идёт через `image-ingestor`
  (как camera-node).
- **EXPLAINABILITY_UX** — advisory-карточки в mobile показывают `text_summary`.
- **UNIFIED_ALERTING** — push-уведомления через alerting-service.
- **IPM** — trap photos → analyzer.

## 9. Правила для ИИ-агентов

### Можно:
- Добавлять новые типы inspections в `mobile_field_inspections.mode`.
- Улучшать offline conflict resolution.

### Нельзя:
- Хранить credentials в app (только session tokens).
- Разрешать прямой доступ в БД с клиента (только через API).
- Использовать GPS для идентификации зоны (ненадёжно в теплице).

## 10. Открытые вопросы

1. Native (Kotlin+Swift) vs React Native vs Flutter? В репо уже есть
   `mobile/` — посмотреть, что там.
2. Speech-to-text: on-device (быстрее, приватнее) vs cloud (точнее)?
3. Нужны ли смарт-очки для hands-free? Маленькая доля use cases, отложить.

---

# Конец MOBILE_AR_CHARTER.md
