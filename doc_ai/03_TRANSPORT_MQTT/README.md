# 03_TRANSPORT_MQTT — MQTT транспорт

Этот раздел содержит документацию по протоколу MQTT, используемому для коммуникации между узлами ESP32 и backend.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [MQTT_SPEC_FULL.md](MQTT_SPEC_FULL.md)
**Полная спецификация MQTT**
- Общая концепция MQTT 2.0
- Структура топиков
- Telemetry (узлы → backend)
- Commands (backend → узлы)
- NodeConfig (backend → узлы)
- Status и LWT
- Heartbeat
- Форматы JSON payload

#### [MQTT_NAMESPACE.md](MQTT_NAMESPACE.md)
**Структура namespace топиков**
- Формат топиков: `hydro/{gh}/{zone}/{node}/{channel}/{type}`
- Правила именования
- Примеры топиков

#### [BACKEND_NODE_CONTRACT_FULL.md](BACKEND_NODE_CONTRACT_FULL.md)
**Контракт между backend и узлами**
- Обязательства backend
- Обязательства узлов
- Обработка ошибок
- Таймауты и retry

### Специализированные документы

#### [COMMAND_VALIDATION_ENGINE.md](COMMAND_VALIDATION_ENGINE.md)
Валидация команд перед отправкой

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура и потоки данных
- **[02_HARDWARE_FIRMWARE](../02_HARDWARE_FIRMWARE/)** — прошивки узлов
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend интеграция

---

## 🎯 С чего начать

1. **Нужна полная спецификация?** → Изучите [MQTT_SPEC_FULL.md](MQTT_SPEC_FULL.md)
2. **Работаете с топиками?** → См. [MQTT_NAMESPACE.md](MQTT_NAMESPACE.md)
3. **Интеграция backend-узлы?** → Прочитайте [BACKEND_NODE_CONTRACT_FULL.md](BACKEND_NODE_CONTRACT_FULL.md)

---

## 📊 Статус и границы

Документы раздела описывают **один канонический MQTT-брокер** на среду (см. `MQTT_SPEC_FULL.md`, `MQTT_NAMESPACE.md`). Распределение узлов по нескольким брокерам и «multi-broker LB» в текущей канонике **не задаются** — при необходимости оформляется отдельной задачей и миграцией протокола.

---

**См. также:** [Главный индекс документации](../INDEX.md)
