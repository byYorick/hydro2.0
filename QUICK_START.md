# Быстрый старт для разработчиков

## 📚 Документация

**Основная документация:** `doc_ai/` (source of truth, редактируется здесь)  
**Mirror документации:** `docs/` (для совместимости, не редактируется вручную)

### Ключевые документы

- **📖 Начните с:** `doc_ai/INDEX.md` — главный индекс документации
- **Архитектура системы:** `doc_ai/SYSTEM_ARCH_FULL.md`
- **Структура проекта:** `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- **Конвенции разработки:** `doc_ai/DEV_CONVENTIONS.md`

### Специфические документы

- **Backend (Laravel):** `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- **Python-сервисы:** `backend/services/PYTHON_SERVICES_ARCH.md`
- **Firmware (ESP32):** `doc_ai/02_HARDWARE_FIRMWARE/`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **MQTT:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **Frontend:** `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- **Android:** `doc_ai/12_ANDROID_APP/`

---

## 🚀 Быстрый запуск

### Backend (Laravel + Python-сервисы)

```bash
make up
```

Для полного чистого dev-refresh с удалением volume, сервисных image и пересборкой без cache.
После `refresh` в local dev в БД остаются только `admin@example.com` и `agronomist@example.com`:

```bash
make refresh
```

Сервисы:
- Laravel: http://localhost:8080
- mqtt-bridge: http://localhost:9000
- automation-engine metrics: http://localhost:9401/metrics
- scheduler metrics: http://localhost:9402/metrics

### Проверка работы

```bash
# Проверка mqtt-bridge
curl -X POST http://localhost:9000/bridge/zones/1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "type": "FORCE_IRRIGATION",
    "params": {"duration_sec": 5},
    "greenhouse_uid": "gh-1",
    "node_id": 1,
    "channel": "pump_in"
  }'
```

---

## 📁 Структура проекта

```
hydro2.0/
├── doc_ai/          # Source of truth документации
├── docs/            # Mirror документации (без ручных правок)
├── backend/         # Backend сервисы
│   ├── laravel/     # Laravel приложение (API Gateway)
│   └── services/    # Python-сервисы
├── firmware/        # Прошивки ESP32
├── mobile/          # Мобильное приложение
├── infra/           # Инфраструктура
├── tools/           # Утилиты
└── configs/         # Конфигурации
```

---

## 🔍 Поиск информации

### Где найти информацию о...

- **Архитектуре системы:** `doc_ai/SYSTEM_ARCH_FULL.md`
- **Python-сервисах:** `backend/services/PYTHON_SERVICES_ARCH.md`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **MQTT протоколе:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **Backend API:** `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- **Firmware структуре:** `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`

---

## ⚠️ Важные замечания

1. **Документацию правим в `doc_ai/`** — это source of truth
2. **`docs/` не редактируем вручную** — это mirror для совместимости
3. **При несоответствиях** приводим код/конфиги в соответствие с документацией
4. **Статусы компонентов** указаны в README файлах (PLANNED, MVP_DONE и т.д.)
5. **MQTT_EXTERNAL_HOST**: в dev по умолчанию используется `host.docker.internal`;
   для ESP32 в реальной сети укажите IP хоста в `MQTT_EXTERNAL_HOST` (на Linux может
   понадобиться явная настройка `host.docker.internal` или явный IP)

## 🛠️ Разработка

### Добавление нового компонента

1. Изучить документацию в `doc_ai/`
2. Создать компонент согласно документации
3. Обновить соответствующий README с ссылками на документацию
4. Указать статус (PLANNED, IN_PROGRESS, MVP_DONE)

### Работа с ИИ-агентами

См. `doc_ai/TASKS_FOR_AI_AGENTS.md` и `doc_ai/DEV_CONVENTIONS.md`

---

## 📞 Полезные ссылки

- Полная архитектура: `doc_ai/SYSTEM_ARCH_FULL.md`
- Конвенции: `doc_ai/DEV_CONVENTIONS.md`
