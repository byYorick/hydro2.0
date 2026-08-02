# OTA_UPDATE_PROTOCOL.md
# Полная спецификация OTA-обновления узлов ESP32 для системы 2.0

Документ описывает безопасный протокол OTA-обновления прошивок узлов ESP32.

Цели:

- централизованное обновление всех узлов;
- контроль версии прошивок;
- безопасный откат при неудаче;
- минимальное влияние на работу теплицы.

Текущий runtime-статус (**planned**):
- в baseline (`firmware/nodes/*`, `firmware/test_node`) OTA-команды и download flow **не** реализованы;
- Laravel: схема `firmware_files` + model/seeder; **нет** `/api/ota/*`, UI, jobs;
- документ = целевая спецификация для внедрения.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 1. Общая схема (target)

Участники:

- **Backend (Laravel)** — хранит бинарники, версии и историю обновлений.
- **Orchestrator (Laravel/AE)** — инициирует обновления, следит за статусами.
- **history-logger** — **единственная** точка публикации OTA-команды в MQTT (как и прочих device/system commands).
- **ESP32-ноды** — принимают команды и скачивают прошивку.

Поток (target):

1. Оператор в UI создаёт запись прошивки и загружает бинарник.
2. Backend сохраняет файл в `storage/app/ota/` и запись в таблице **`firmware_files`** (не `firmware_images`).
3. Orchestrator получает сигнал (webhook/endpoint), что доступна новая версия.
4. Публикация OTA в MQTT — **только через history-logger** (`POST /commands` или dedicated system-publish API HL), **не** прямой MQTT publish из Python/Laravel.
5. Узел ESP32: получает команду → скачивает бинарник (signed URL — target) → OTA → результат в MQTT.

---

## 2. Идентификаторы прошивок

Таблица **`firmware_files`** (as-is schema; runtime API — planned):

- `id` — PK;
- `node_type` — тип узла (`ph`, `ec`, `climate`, `irrig`, `light`, `relay`, …);
- `version` — семантическая версия (`1.0.3`);
- `file_path` — путь до бинарника (канон storage: `storage/app/ota/`);
- `checksum_sha256` — контрольная сумма;
- `release_notes` — TEXT;
- `created_at`.

Target-поля (ещё не в миграции): человекочитаемый `uid` / `firmware_uid` для MQTT payload.

Узел хранит у себя:

- `firmware_version` (строка);
- `firmware_uid` (опционально);
- `last_update_at`.

---

## 3. MQTT-команда OTA

Используется системный топик:

```text
hydro/system/ota/{node_uid}
```

Примечание: использование этого topик-контракта в текущем runtime не включено по умолчанию;
перед запуском OTA в production требуется отдельная реализация и e2e/HIL-валидация.

Payload (пример):

```json
{
 "cmd": "OTA_UPDATE",
 "firmware_uid": "esp32-ph-v1.0.3",
 "file_url": "https://backend/…/ota/…signed…",
 "checksum_sha256": "abc123…",
 "ttl_ms": 600000,
 "request_id": "ota-2025-01-01-12-00-00-001"
}
```

Target security (см. `SECURITY_ARCHITECTURE.md` §6.1 — **planned**): signed URL, HMAC команды/запроса, verify SHA256 + version на узле.

Требования (target):

- Узел обязан проверить TTL, URL, checksum после загрузки; HMAC/signed URL — при реализации firmware OTA.

---

## 4. Поведение узла ESP32

1. Получить команду из `hydro/system/ota/{node_uid}`.
2. Проверить `ttl_ms` и другие поля.
3. Скачать файл по `file_url` (HTTPS/HTTP, размер ограничен).
4. Подсчитать SHA-256 и сравнить с `checksum_sha256`.
5. Если всё хорошо:
 - выполнить OTA-обновление;
 - сохранить новую версию в NVS;
 - отправить статус:

```text
hydro/system/ota/{node_uid}/status
```

```json
{
 "request_id": "ota-2025-01-01-12-00-00-001",
 "status": "OK",
 "old_version": "1.0.2",
 "new_version": "1.0.3",
 "ts": 1737355604000
}
```

6. Если ошибка:
 - не обновляться;
 - отправить статус с ошибкой и кодом причины.

---

## 5. Backend / Python-логика

- Backend:
 - хранит прошивки и их метаданные;
 - предоставляет защищённые URL для скачивания;
 - ведёт историю обновлений по узлам.
- Python-сервис:
 - по запросу оператора или плану обновлений:
 - формирует список узлов для OTA;
 - отправляет MQTT-команды;
 - слушает `status`-топики и обновляет БД.

---

## 6. Правила для ИИ-агентов

1. Не менять формат базовой MQTT-команды OTA без обновления этого документа.
2. Не заставлять узлы скачивать прошивки из непроверенных источников.
3. Не добавлять тяжёлую логику в код ESP32, связанную с управлением версиями — всё это на стороне backend/Python.

OTA в этой системе — **управляемый, централизованный процесс**, а не хаотичное обновление «по месту».
