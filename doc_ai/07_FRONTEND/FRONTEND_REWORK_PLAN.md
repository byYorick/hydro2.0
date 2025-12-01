# FRONTEND_REWORK_PLAN.md
# План доработки фронтенда после анализа backend 2.0

## 1. Цель документа

Синхронизировать развитие фронтенда с архитектурой backend 2.0 (Laravel + Python-сервисы) и сформировать приоритетный бэклог. План фокусируется на:

- строгом соблюдении ролей backend как «единого центра правды»;

- устранении разрывов между UI и REST/WebSocket API;

- подготовке фронтенда к realtime-режиму и управлению зонами.

## 2. Что даёт backend (краткое резюме)

По архитектурной документации backend обеспечивает следующие возможности:

- **API Gateway (Laravel)**: REST `\/api/*`, WebSocket/Broadcasting, управление конфигурацией, пользователями и рецептами.【F:backend/README.md†L6-L33】

- **Application & Domain слой**: сервисы для CRUD теплиц, зон, рецептов, алертов, команд. Валидации инвариантов (зона не может использовать два узла, рецепты без пересечений).【F:doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md†L26-L116】

- **Интеграция с Python-сервисами**: backend владеет конфигурацией; Python пишет телеметрию в PostgreSQL, выполняет команды и уведомляет backend о результатах. Фронтенд взаимодействует только с backend API и WebSocketами.【F:doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md†L118-L199】

- **Monitoring/Telemetry**: Prometheus, Grafana и TimescaleDB уже развёрнуты, есть агрегации и retention; Laravel команды (`telemetry:cleanup-raw`, `telemetry:aggregate`) готовят данные для графиков.【F:backend/README.md†L35-L76】

Эти возможности позволяют фронтенду строить realtime UI без прямого доступа к MQTT.

## 3. Обнаруженные пробелы фронтенда

На основе `FRONTEND_AUDIT.md` и UI-спецификации:

1. **Dashboard**: ✅ Ролевые дашборды реализованы, последние события добавлены. ⏳ Мини-графики и heatmap зон планируются в Волне 3.

2. **Command Palette**: ✅ Базовый функционал реализован (Ctrl+K, поиск, навигация). ⏳ Быстрые действия и fuzzy search планируются в Волне 4.

3. **Zone Detail**: ✅ Cycles блок использует реальные данные из backend. ⏳ Forms для параметров команд планируются в Волне 2.

4. **Локализация**: ✅ Полностью выполнена - все тексты на русском языке.

5. **Ошибки UX**: ✅ Исправлено - используется `router.reload()`, добавлены Toast уведомления. ⏳ Forms для параметров команд планируются в Волне 2.

6. **Хедер статусов**: ✅ Реализован `HeaderStatusBar.vue` с индикаторами WebSocket, MQTT, DB, Core.

## 4. План доработки (5 волн)

### Волна 1 — Синхронизация базовой архитектуры ✅ ВЫПОЛНЕНО

- ✅ **Инвентаризация API**: создан `API_MAPPING.md` с полным маппингом endpoints.

- ✅ **State-management**: реализованы composables (`useZones`, `useTelemetry`, `useApi`, и др.) с кешированием и оптимизацией.

- ✅ **Локализация навигации**: все тексты переведены на русский, создана система локализации `utils/i18n.js`.

- ✅ **Хедер статусов**: реализован `HeaderStatusBar.vue` с индикаторами WebSocket, MQTT, DB, Core.

### Волна 2 — Zone Detail ↔ backend use-cases

- ⏳ **Actions drawer**: заменить захардкоженные параметры команд на формы, подгружая допустимые параметры из backend (например, `available_actions` для зоны).

- ⏳ **Команды и ответы**: интегрировать WebSocket/echo канал `commands.{zoneId}` для отображения статуса и ошибок; добавить уведомления.

- ✅ **Cycles виджет**: реализован - использует реальные данные `last_run`, `next_run`, `strategy`, `interval` из backend через API endpoint `/api/zones/{id}/cycles`.

### Волна 3 — Dashboard и realtime телеметрия

- **Мини-графики**: использовать агрегированные данные Timescale (`telemetry/aggregates` endpoint) для отображения 24h mini charts.

- **Heatmap зон**: визуализировать статусы зон (RUNNING, PAUSED, ALARM) с использованием props `zones_status_summary`.

- **Events & alerts stream**: подписать фронтенд на Laravel Broadcasting канал `events.global` и вывести последние события без перезагрузки.

### Волна 4 — Command Palette и глобальные действия

- **Ctrl+K**: подключить компонент к спискам зон/узлов/рецептов (REST `/api/search`); реализовать fuzzy search.

- **Быстрые действия**: описать action descriptors в backend (название, endpoint, параметры) и отправлять через Palette с подтверждением.

- **Keyboard navigation**: добавить shortcuts для часто используемых экранов (Zones, Alerts, AI Panel).

### Волна 5 — UX & технические улучшения

- ✅ **Toast/notifications**: реализованы через `useToast` composable и `ToastContainer` компонент.

- ⏳ **Form validation**: использовать `useForm` от Inertia с серверной валидацией для команд/рецептов.

- ✅ **Testing**: реализованы unit тесты для ключевых компонентов (Vitest).

## 5. Зависимости и контрольные точки

- Каждая волна завершается обновлением `FRONTEND_UI_UX_SPEC.md` (если появились новые элементы) и `FRONTEND_TESTING.md` (если изменились сценарии).

- Backend изменения фиксируются в `API_SPEC_FRONTEND_BACKEND_FULL.md`; без их обновления фича не считается завершённой.

- Наличие realtime функциональности требует настройки Laravel Reverb/echo client; DevOps команда должна подтвердить конфигурацию перед Волной 3.

## 6. Ожидаемый результат

После выполнения плана фронтенд будет:

- полностью русифицирован и соответствовать UX-спецификации;

- работать поверх актуальных backend use-cases без дублирования логики;

- поддерживать realtime телеметрию, команды и события;

- иметь понятный бэклог, разделённый на волны для последовательной реализации.

## 7. Цепочка определения статусов для хедера

Чтобы иконки ONLINE/OFFLINE в шапке были привязаны к реальным потокам данных, используется единая цепочка:

1. **Core/App + Database**: эндпоинт `GET /api/system/health` (Laravel `SystemController::health`) выполняет быстрый `SELECT 1`. Ответ содержит `app` и `db` ключи, которые напрямую мапятся на зелёный/красный статус Core и базы в хедере. Период обновления — 30–60 секунд, с fallback к toast при неудаче.【F:backend/laravel/app/Http/Controllers/SystemController.php†L8-L33】【F:doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md†L472-L544】

2. **WebSocket**: клиент `laravel-echo` подключается к Reverb (`ws://localhost:6001`) и публикует `connected`/`disconnecting` события. Хедер подписывается на эти события и обновляет иконку WebSocket в реальном времени, поскольку соединение является обязательным для получения telemetry/events.【F:doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md†L616-L644】

3. **MQTT**: узлы публикуют `status` (ONLINE) сразу после MQTT-подключения и LWT `offline` при обрыве. Backend (через Python-сервис + Laravel) получает эти топики, обновляет `nodes.status`, транслирует `NodeStatusUpdated` в WebSocket и хранит агрегаты (например, `zones_status_summary`). Хедер слушает глобальный WebSocket канал и выводит «MQTT онлайн», если суммарно все узлы в статусе ONLINE за последние 30 секунд; иначе отображает предупреждение (частичное падение) или OFFLINE при массовом LWT.【F:doc_ai/01_SYSTEM/DATAFLOW_FULL.md†L184-L239】【F:doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md†L625-L644】

4. **Цепочка обновления**: Node → MQTT брокер → Backend status listener → PostgreSQL/Redis → Laravel Reverb событие → HeaderStatusBar. Если на любом шаге цепочка рвётся (нет статуса, база недоступна, Reverb недоступен), соответствующая иконка переходит в OFFLINE/UNKNOWN, что помогает оператору мгновенно диагностировать проблему без выхода из UI.【F:doc_ai/01_SYSTEM/DATAFLOW_FULL.md†L27-L340】

Иконки рекомендуется стилизовать через `status-dot` компонент (зелёный = ONLINE, красный = OFFLINE, жёлтый = DEGRADED) и снабжать всплывающими подсказками с последним временем обновления.

