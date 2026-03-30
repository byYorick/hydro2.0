# 01_SYSTEM — Системная архитектура

Этот раздел содержит высокоуровневую системную архитектуру и логику работы системы hydro 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [LOGIC_ARCH.md](LOGIC_ARCH.md)
**Логическая модель системы** (Теплица → Зоны → Ноды → Каналы)
- Иерархия сущностей
- Роли компонентов
- Логические потоки
- Взаимодействие с рецептами

#### [DATAFLOW_FULL.md](DATAFLOW_FULL.md)
**Полные потоки данных**
- Telemetry Flow (узлы → backend)
- Command Flow (backend → узлы)
- Config Flow (`config_report`: узлы → backend)
- Status/LWT Flow
- Heartbeat Flow
- Events Flow
- WebSocket Flow

#### [NODE_LIFECYCLE_AND_PROVISIONING.md](NODE_LIFECYCLE_AND_PROVISIONING.md)
**Жизненный цикл узла**
- Состояния узла (MANUFACTURED → ACTIVE → DECOMMISSIONED)
- Идентификаторы узла
- Этапы жизненного цикла
- Provisioning и регистрация

#### [01_PROJECT_STRUCTURE_PROD.md](01_PROJECT_STRUCTURE_PROD.md)
**Структура боевого проекта**
- Общая структура монорепозитория
- Организация firmware, backend, mobile, infra
- Конфигурационные файлы
- Инструменты и утилиты

### Вспомогательные документы

#### [REPO_MAPPING.md](REPO_MAPPING.md)
Маппинг репозиториев и компонентов

#### [NODE_ASSIGNMENT_LOGIC.md](NODE_ASSIGNMENT_LOGIC.md)
Логика привязки узлов к зонам

#### [NODE_ADDITION_AND_ACTIVATION_FLOW.md](NODE_ADDITION_AND_ACTIVATION_FLOW.md)
Добавление и активация узла в системе

#### [NODE_DETACH_IMPLEMENTATION.md](NODE_DETACH_IMPLEMENTATION.md)
Реализация отвязки узлов от зон

---

## 🔗 Связанные разделы

- **[02_HARDWARE_FIRMWARE](../02_HARDWARE_FIRMWARE/)** — прошивки и железо
- **[03_TRANSPORT_MQTT](../03_TRANSPORT_MQTT/)** — MQTT транспорт
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend архитектура
- **[05_DATA_AND_STORAGE](../05_DATA_AND_STORAGE/)** — модель данных

---

## 🎯 С чего начать

1. **Новичок в проекте?** → Начните с [LOGIC_ARCH.md](LOGIC_ARCH.md)
2. **Нужно понять потоки данных?** → Изучите [DATAFLOW_FULL.md](DATAFLOW_FULL.md)
3. **Работаете с узлами?** → Прочитайте [NODE_LIFECYCLE_AND_PROVISIONING.md](NODE_LIFECYCLE_AND_PROVISIONING.md)
4. **Нужна структура проекта?** → См. [01_PROJECT_STRUCTURE_PROD.md](01_PROJECT_STRUCTURE_PROD.md)

---

## 📊 Статус документов

Все документы в этом разделе имеют статус **SPEC_READY** — спецификации готовы для реализации.

---

**См. также:** [Главный индекс документации](../INDEX.md)
