# Быстрый старт для разработчиков

## 📚 Документация

**Основная документация:** `doc_ai/` (эталон, не изменяется)  
**Mirror документации:** `docs/` (для совместимости)

### Ключевые документы

- **📖 Начните с:** `doc_ai/INDEX.md` — главный индекс документации
- **Архитектура системы:** `doc_ai/SYSTEM_ARCH_FULL.md`
- **Структура проекта:** `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- **Конвенции разработки:** `doc_ai/DEV_CONVENTIONS.md`
- **Roadmap:** `doc_ai/ROADMAP_2.0.md`
- **Статус реализации:** `doc_ai/IMPLEMENTATION_STATUS.md`

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
cd backend
docker compose -f docker-compose.dev.yml up -d --build
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
├── doc_ai/          # Эталонная документация (не изменяется)
├── docs/            # Mirror документации
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

1. **Документация в `doc_ai/` не изменяется** — это эталон
2. **Все изменения** вносятся в код и README файлы проекта
3. **При несоответствиях** приводим проект в соответствие с документацией
4. **Статусы компонентов** указаны в README файлах (PLANNED, MVP_DONE и т.д.)

---

## 📊 Статус проекта

- **Синхронизация:** ✅ Завершена (2025-01-27)
- **План синхронизации:** `doc_ai/SYNC_PLAN.md`
- **Отчет о несоответствиях:** `doc_ai/INCONSISTENCIES_REPORT.md`

---

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
- Roadmap: `doc_ai/ROADMAP_2.0.md`
- Статус реализации: `doc_ai/IMPLEMENTATION_STATUS.md`

