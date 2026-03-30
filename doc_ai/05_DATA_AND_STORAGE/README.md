# 05_DATA_AND_STORAGE — Данные и хранилища

Этот раздел содержит документацию по модели данных, телеметрии и политикам хранения.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [DATA_MODEL_REFERENCE.md](DATA_MODEL_REFERENCE.md)
**Полный справочник моделей данных**
- Общая архитектура данных
- Таблицы теплиц и зон
- Таблицы узлов
- Таблицы телеметрии
- Таблицы рецептов
- Таблицы команд
- Таблицы пользователей
- Связи и ограничения

#### [TELEMETRY_PIPELINE.md](TELEMETRY_PIPELINE.md)
**Пайплайн телеметрии**
- Поток данных от узлов до БД
- Батчинг и upsert
- Обновление последних значений
- Retention политики

#### [DATA_RETENTION_POLICY.md](DATA_RETENTION_POLICY.md)
**Политики хранения данных**
- Retention для телеметрии
- Retention для событий
- Retention для команд
- Архивация данных

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура и логика
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend интеграция
- **[06_DOMAIN_ZONES_RECIPES](../06_DOMAIN_ZONES_RECIPES/)** — доменная логика

---

## 🎯 С чего начать

1. **Модель данных?** → Изучите [DATA_MODEL_REFERENCE.md](DATA_MODEL_REFERENCE.md)
2. **Телеметрия?** → См. [TELEMETRY_PIPELINE.md](TELEMETRY_PIPELINE.md)
3. **Хранение данных?** → Прочитайте [DATA_RETENTION_POLICY.md](DATA_RETENTION_POLICY.md)

---

## 📊 Статус документов

Все документы имеют статус **SPEC_READY** — спецификации готовы для реализации.

---

**См. также:** [Главный индекс документации](../INDEX.md)
