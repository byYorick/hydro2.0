# Структура hydro 2.0 (документация)

**Дата обновления:** 2026-08-02

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

Этот архив содержит спецификацию системы **hydro 2.0** — без разделения на V3/V4.
Все рабочие документы считаются частью одной актуальной версии 2.0.

## 🚀 Начало работы

**Для быстрой навигации используйте [INDEX.md](INDEX.md)** — главный индекс всей документации.

## Статусы документов

В навигации (INDEX / section README) по возможности отражается роль документа:

| Статус | Значение |
|--------|----------|
| `canonical` | Нормативный source of truth для темы; приоритет при конфликте |
| `guide` | Операционный гайд / how-to; не переопределяет канон |
| `plan` | План, proposal, roadmap, audit-findings к обсуждению/внедрению |
| `superseded` | Заменён каноном; оставлен для истории, не использовать как SoT |
| `archive` | Исторический отчёт/черновик в `00_ARCHIVE/` |

Не каждый из ~240 файлов обязан иметь метку; приоритет — сироты, планы и явные противоречия.

## Корень
- **[INDEX.md](INDEX.md)** — главный индекс документации (начните отсюда!)
- `SYSTEM_ARCH_FULL.md` — главный входной файл по архитектуре системы 2.0 (`canonical`)
- `ARCHITECTURE_FLOWS.md` — защищённые pipeline и инварианты (`canonical`)
- `DEV_CONVENTIONS.md` — конвенции разработки (`canonical`)
- `TASKS_FOR_AI_AGENTS.md` — постановка задач для ИИ (`guide`)
- `11_WEBSOCKET_ARCHITECTURE.md` — WebSocket/Reverb и real-time UI (`canonical`)
- `IMPLEMENTATION_STATUS.md` — сводный статус реализации (`guide`)
- `README_STRUCTURE.md` — это описание структуры папок
- Планы в корне (`plan`): `ROADMAP_2.0.md`, `DEVELOPMENT_PRIORITIES.md`, `AGRO_AUTONOMY_MASTER_PLAN.md`, `SYNC_PLAN.md`, `FIRMWARE_OPTIMIZATION_PLAN.md`, audit-планы `AUDIT_*.md`

## 00_ARCHIVE
Исторические отчёты и промежуточные материалы (**статус `archive`**). Не являются source of truth для текущей разработки.

Структура (~57 markdown-файлов):
- `REPORTS/` — аудиты кода/документации, cleanup, gaps, backend/python отчёты;
- `PHASE_REPORTS/` — промежуточные отчёты фаз рефакторинга backend;
- `FRONTEND_REPORTS/` — аудиты и доработки frontend.

Точка входа: [00_ARCHIVE/README.md](00_ARCHIVE/README.md). Актуальный статус реализации — `IMPLEMENTATION_STATUS.md` в корне `doc_ai/`.

## 01_SYSTEM
Высокоуровневая системная архитектура и потоки данных:
- общая логическая модель домена;
- описание глобальных dataflow;
- жизненный цикл / assignment / detach узлов;
- планы и proposal (не все `canonical` — см. README раздела).

## 02_HARDWARE_FIRMWARE
Железо и прошивки узлов:
- общая аппаратная архитектура;
- структура прошивок и протоколы узлов;
- описание типов нод (pH, EC, климат, полив, свет);
- Wi‑Fi/OTA и диагностика;
- NodeConfig / config_report / coding standards.

## 03_TRANSPORT_MQTT
Транспорт и MQTT-протокол:
- структура топиков и namespace;
- контракты между backend и узлами;
- валидация команд и соблюдение транспортных инвариантов;
- планы масштабирования (multi-broker) — вне текущей каноники.

## 04_BACKEND_CORE
Ядро backend-приложения:
- архитектура Laravel-приложения;
- Python-сервисы и AE3 (`ae3lite.md` — canonical runtime);
- REST/API‑слой, history-logger, error codes;
- стек и варианты деплоя (в т.ч. Docker);
- планы рефакторинга / reliability (status `plan`).

## 05_DATA_AND_STORAGE
Данные и хранилища:
- модель данных и связи;
- сбор и хранение телеметрии;
- политики хранения (retention).

## 06_DOMAIN_ZONES_RECIPES
Доменные правила, зоны и рецепты:
- контроллеры зон;
- движок рецептов и управление водой;
- планировщики, события и алерты;
- correction / effective targets / control modes;
- пресеты и шаблоны зон.

## 07_FRONTEND
Фронтенд и UI/UX:
- архитектура SPA/панели управления;
- сценарии работы оператора и администратора;
- real‑time обновление состояния;
- планы redesign / wizard / scheduler cockpit (`plan`).

## 08_SECURITY_AND_OPS
Безопасность и эксплуатация:
- аутентификация/авторизация, роли и права;
- мониторинг и логирование;
- резервное копирование и восстановление;
- runbooks и CI/CD strategy.

## 09_AI_AND_DIGITAL_TWIN
AI и цифровой двойник:
- общая AI‑архитектура;
- оптимизация режимов, симуляция зон;
- pipeline plans и charters (часть — `plan` / charter, не полный runtime-канон).

## 10_AI_DEV_GUIDES
Гайды по работе с ИИ (`guide`):
- как использовать ассистента для генерации кода backend/firmware;
- рекомендации по работе с схемой БД, MQTT и контроллерами зон;
- шаблоны задач и prompting.

## 12_ANDROID_APP
Android-приложение:
- архитектура клиента;
- экраны и grow-cycle UI;
- интеграция с backend API.

См. [12_ANDROID_APP/README.md](12_ANDROID_APP/README.md).

## 13_TESTING
Тестирование и E2E:
- обзор стратегии тестирования;
- E2E guide / scenarios / setup / auth;
- симулятор узлов (`NODE_SIM`);
- troubleshooting.

См. [13_TESTING/README.md](13_TESTING/README.md).

## Корень `doc_ai/` (вне нумерованных папок)

Сквозные документы перечислены в блоке **Корень** выше и в [INDEX.md](INDEX.md).
Нумерация разделов: `01`–`10`, затем `12`–`13` (отдельного раздела `11_*` нет — WebSocket лежит в корне как `11_WEBSOCKET_ARCHITECTURE.md`).
