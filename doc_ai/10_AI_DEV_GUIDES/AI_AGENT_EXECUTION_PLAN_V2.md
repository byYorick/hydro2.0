# AI_AGENT_EXECUTION_PLAN_V2.md
# План выполнения для ИИ-агента (Risk-First)

**Дата:** 2026-02-07  
**Статус:** Active  
**Фокус:** безопасность, управляемость, снижение регрессионных рисков.

---

## 1) Формат исполнения этапа (обязательный)

Для каждого этапа ИИ-агент обязан фиксировать:

1. `Scope` — какие файлы и подсистемы затрагиваются.
2. `Changes` — список правок по файлам.
3. `Checks` — какие проверки выполнены (lint/tests/smoke).
4. `Gate` — критерий завершения этапа (pass/fail).
5. `Rollback` — как откатить изменения этапа.

---

## 2) Этапы

### Этап S0: Baseline и gates (1 итерация)

- Scope:
  - `backend/laravel`, `backend/services`, `.github/workflows`.
- Changes:
  - только диагностика и фиксация baseline-метрик.
- Checks:
  - сбор метрик размера файлов, техдолга типизации, тестового покрытия.
- Gate:
  - baseline зафиксирован и пригоден для сравнения.
- Rollback:
  - не требуется (без кодовых изменений).

### Этап S1: Security quick wins (2-4 итерации)

- Scope:
  - доступы (`InfrastructureInstanceController`, `ZoneAccessHelper`),
  - сервисные endpoint-ы E2E/auth,
  - исходящие HTTP вызовы bridge,
  - backup-команды.
- Changes:
  - устранение очевидных дыр без изменения протокола.
- Checks:
  - минимум `php -l` на измененных файлах,
  - целевые unit/feature тесты (при доступной среде).
- Gate:
  - нет открытых `CRITICAL/HIGH` из quick wins.
- Rollback:
  - revert конкретных commit/patch по этапу.

### Этап S2: Снижение сложности кода (3-6 итераций)

- Scope:
  - top-N крупных файлов frontend/backend/python.
- Changes:
  - декомпозиция без изменения внешних контрактов.
- Checks:
  - regression tests, smoke e2e.
- Gate:
  - уменьшение размера top-файлов минимум на 30%.
- Rollback:
  - пофайлово, через отдельные PR-итерации.

### Этап S3: Контракты и типизация (3-5 итераций)

- Scope:
  - API/WS контракты + TS-типы.
- Changes:
  - замена `any` в критичных местах, блокирующие contract tests.
- Checks:
  - typecheck, contract tests.
- Gate:
  - `any/as any` и `@ts-ignore` снижены до целевых значений.
- Rollback:
  - отключение новых блокирующих правил и частичный revert.

### Этап S4: CI и репо-гигиена (2-3 итерации)

- Scope:
  - `.github/workflows`, `.gitignore`, generated artifacts.
- Changes:
  - чистка репозитория и усиление quality gates.
- Checks:
  - полный CI pipeline.
- Gate:
  - стабильный CI и отсутствие generated артефактов в git.
- Rollback:
  - откат изменений CI workflow отдельным patch.

---

## 3) Текущий прогресс

### Выполнено (S1, итерация 1)

1. Закрыты TODO по проверке доступа к `greenhouse` в инфраструктурных endpoint-ах.
2. E2E auth endpoint ограничен только `testing/e2e`.
3. Добавлена политика SSL-verify для Python bridge:
   - по умолчанию verify включен;
   - bypass возможен через `PY_API_VERIFY_SSL=false`;
   - в `production` bypass принудительно блокируется.
4. Устранен shell-injection риск в команде сжатия backup (`gzip` + `escapeshellarg`).

### Выполнено (S1, итерация 2)

1. Добавлен feature-flag `ACCESS_CONTROL_MODE` (`legacy|shadow|enforce`).
2. Реализован `shadow`/`enforce` режим в `ZoneAccessHelper` с fallback на `legacy`, если pivot-таблицы отсутствуют.
3. Добавлены связи `User::zones()` и `User::greenhouses()`.
4. Добавлены миграции:
   - `user_greenhouses`
   - `user_zones`
5. Обновлен `DATA_MODEL_REFERENCE.md` (раздел Users & Roles и ключевые связи).
6. Добавлен unit-тест `ZoneAccessHelperTest` и пройден в docker.
7. Прогнаны смежные feature-тесты (`SystemControllerTest`, `TelemetryTest`) в docker.

### Следующая итерация (S1, итерация 3)

1. Добавить feature-тесты для API сценариев `greenhouse/zone` в enforce-режиме.
2. Вынести shadow mismatch аудит в отдельный лог-канал/метрику.
3. Подготовить migration-safe rollout-инструкцию для включения `enforce` в staging/prod.

### Выполнено (S1, итерация 3)

1. Добавлены feature-тесты API для `enforce` доступа:
   - `InfrastructureAccessEnforceModeTest`
2. Shadow аудит вынесен в отдельный log-channel:
   - `access_shadow`
3. Подготовлена отдельная rollout-инструкция:
   - `ACCESS_CONTROL_ENFORCE_ROLLOUT.md`

### Следующая итерация (S2, итерация 1)

1. Начать декомпозицию крупных файлов по приоритету:
   - `ZoneSimulationModal.vue`
   - `useWebSocket.ts`
   - `echoClient.ts`
2. Ввести ограничение на размер новых/измененных файлов с авто-проверкой в CI.

### Выполнено (S2, итерация 1, частично)

1. Выполнена декомпозиция realtime-конфига Echo:
   - из `echoClient.ts` вынесена конфигурационная логика в `echoConfig.ts`;
   - `echoClient.ts` переведен на импорт `buildEchoConfig/resolve*` из нового модуля.
2. Добавлен CI guard размера файлов:
   - `backend/laravel/scripts/check-file-size-guard.sh`;
   - подключен в `.github/workflows/ci.yml`;
   - добавлен `fetch-depth: 0` для корректного diff по base-ветке.
3. Локальная проверка этапа:
   - `npx eslint resources/js/utils/echoClient.ts resources/js/utils/echoConfig.ts` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 2)

1. Декомпозировать `useWebSocket.ts`:
   - вынести реестр подписок/каналов в отдельный модуль;
   - сократить когнитивную сложность resubscribe/reconciliation paths.
2. Декомпозировать `ZoneSimulationModal.vue`:
   - вынести API/состояние симуляции в composable;
   - разделить UI-части (форма, прогресс, отчеты) на подпакеты.

### Выполнено (S2, итерация 2, частично)

1. Начата декомпозиция `useWebSocket.ts`:
   - вынесен snapshot/reconciliation registry в `resources/js/ws/snapshotRegistry.ts`;
   - `useWebSocket.ts` переведен на импортированные операции реестра (`get/set/has`, stale-check, handlers).
2. Вынесен lifecycle подписок в отдельный модуль:
   - `resources/js/ws/subscriptionLifecycle.ts` (add/remove subscriptions, ref-count, detach logic);
   - `resources/js/ws/subscriptionTypes.ts` (общие типы каналов/подписок).
3. Начата декомпозиция `ZoneSimulationModal.vue`:
   - вынесена presentation-логика (computed по прогрессу/статусу/отчету) в `resources/js/composables/useSimulationPresentation.ts`;
   - компонент переведен на `useSimulationPresentation(...)` и `mapActiveSimulationStatus(...)`.
4. Продолжена декомпозиция `ZoneSimulationModal.vue`:
   - вынесена drift-логика (`node-sim`) в `resources/js/composables/useSimulationDrift.ts`;
   - компонент переведен на `useSimulationDrift(...)` и `markDriftTouched(...)`.
5. Продолжена декомпозиция `ZoneSimulationModal.vue`:
   - вынесена логика event-feed (SSE + reconnect + fallback polling) в `resources/js/composables/useSimulationEventFeed.ts`;
   - компонент переведен на `useSimulationEventFeed(...)`.
6. Исправлены старые typecheck-ошибки:
   - `CycleControlPanel.vue`: добавлены типизированные поля `current_phase_id/currentPhase`;
   - `Greenhouses/Show.vue`: добавлен индексный ключ в `PageProps`;
   - `ZoneOverviewTab.vue` и `ZoneCycleTab.vue`: `variant/cycleStatusVariant` расширены до `BadgeVariant`.
7. Обновлен reset-hook тестовых экспортов:
   - `__testExports.reset()` теперь очищает snapshot registry через `clearSnapshotRegistry()`.
8. Метрика декомпозиции:
   - `useWebSocket.ts`: `1327 -> 1146` строк.
   - `ZoneSimulationModal.vue`: `1951 -> 1564` строк.
9. Проверки:
   - `npx eslint resources/js/composables/useWebSocket.ts resources/js/ws/snapshotRegistry.ts resources/js/ws/subscriptionLifecycle.ts resources/js/ws/subscriptionTypes.ts resources/js/utils/echoClient.ts resources/js/utils/echoConfig.ts` — pass;
   - `npx eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationPresentation.ts resources/js/composables/useSimulationDrift.ts resources/js/composables/useSimulationEventFeed.ts ...` — pass (без errors, warnings legacy-стиля в шаблоне);
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.
   - `npm run typecheck` — pass.

### Выполнено (S2, итерация 2, дополнение)

1. Продолжена декомпозиция `ZoneSimulationModal.vue`:
   - submit/payload-блок вынесен в `resources/js/composables/useSimulationSubmit.ts`;
   - в composable выделены:
     - `buildSimulationPayload(form, drift)` (нормализация payload и фильтрация `null`);
     - `submitZoneSimulation(zoneId, form, drift)` (единый вызов API + классификация ответа `queued/completed/invalid`).
2. `ZoneSimulationModal.vue` переведен на `useSimulationSubmit(...)`:
   - `onSubmit` теперь оркестрирует UI-state и post-submit поведение;
   - ручная inline-сборка payload удалена.
3. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1564 -> 1502` строк.
   - Новый composable: `useSimulationSubmit.ts` (175 строк).
4. Проверки:
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel npm run typecheck` — pass;
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel sh -lc './node_modules/.bin/eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationSubmit.ts'` — pass (0 errors, legacy warnings сохранены);
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 3)

1. Вынести `polling/status sync` логику из `ZoneSimulationModal.vue` в отдельный composable (`useSimulationPolling`).
2. Вынести `recipes/defaults` загрузку в отдельный composable (`useSimulationRecipes`).
3. После вынесения двух блоков повторно прогнать `typecheck + file-size-guard` и зафиксировать снижение размера `ZoneSimulationModal.vue`.

### Выполнено (S2, итерация 3, частично)

1. Зачищены legacy eslint warnings во фронтенд-части:
   - `ZoneSimulationModal.vue`: исправлены `vue/attributes-order` и `vue/singleline-html-element-content-newline`;
   - `ZoneCycleTab.vue`: исправлен `vue/max-attributes-per-line`;
   - `Zones/Show.vue`: удален неиспользуемый `fetchZone` (`@typescript-eslint/no-unused-vars`);
   - `Zones/Simulation.vue`: зафиксировано исключение для snake_case Inertia props (`active_grow_cycle`, `active_simulation`) с точечным комментарием.
2. Проверки:
   - `eslint . --ext .ts,.tsx,.vue -f compact`: warnings = 0, остаются 3 legacy errors в `PlantCreateModal.vue` и `Pages/Logs/Index.vue`;
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 3, продолжение)

1. Закрыть оставшиеся legacy eslint errors:
   - `resources/js/Components/PlantCreateModal.vue` (`vue/no-dupe-keys`);
   - `resources/js/Pages/Logs/Index.vue` (`no-extra-semi`).
2. Повторно прогнать полный `eslint` и зафиксировать `errors = 0, warnings = 0`.

### Выполнено (S2, итерация 3, продолжение)

1. Закрыты оставшиеся legacy eslint errors:
   - `PlantCreateModal.vue`: устранен конфликт `taxonomies` (prop/computed), computed переименован в `taxonomyOptions`;
   - `Pages/Logs/Index.vue`: убраны проблемные leading-выражения с `window` и заменены на безопасный `win` alias.
2. Проверки:
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 4)

1. Вынести `polling/status sync` логику из `ZoneSimulationModal.vue` в отдельный composable (`useSimulationPolling`).
2. Вынести `recipes/defaults` загрузку в отдельный composable (`useSimulationRecipes`).
3. Повторно прогнать `lint + typecheck + file-size-guard` и зафиксировать снижение размера `ZoneSimulationModal.vue`.

### Выполнено (S2, итерация 4)

1. `ZoneSimulationModal.vue` декомпозирован дальше:
   - вынесен блок polling/status sync в `resources/js/composables/useSimulationPolling.ts`;
   - вынесен блок recipes/defaults (поиск, debounce, cache, default-sync) в `resources/js/composables/useSimulationRecipes.ts`.
2. Компонент переведен на новые composable:
   - `useSimulationPolling(...)` управляет polling и sync active simulation;
   - `useSimulationRecipes(...)` управляет списком рецептов и применением recipe defaults.
3. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1522 -> 1286` строк.
   - Добавлены новые файлы:
     - `useSimulationPolling.ts` (187 строк),
     - `useSimulationRecipes.ts` (216 строк).
4. Проверки:
   - `eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationRecipes.ts resources/js/composables/useSimulationPolling.ts` — pass;
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 5)

1. Вынести из `ZoneSimulationModal.vue` общий reset runtime-state в отдельный composable/helper, убрать дублирование в `watch/onUnmounted/onSubmit`.
2. Вынести форматтеры (`formatTimestamp/formatReportValue/...`) в утилиту `simulationFormatters`.
3. Зафиксировать новую метрику размера файла и повторить `lint + typecheck + guard`.

### Выполнено (S2, итерация 5)

1. `ZoneSimulationModal.vue` дополнительно упрощен:
   - вынесен runtime-state reset в `resources/js/composables/useSimulationRuntimeState.ts`;
   - вынесены форматтеры/классификатор уровня в `resources/js/utils/simulationFormatters.ts`.
2. Компонент переведен на импортированные helper/composable:
   - удалено дублирование reset-логики в `watch/isVisible`, `onUnmounted`, `onSubmit`;
   - удалены локальные функции форматирования и `simulationLevelClass`.
3. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1286 -> 1226` строк.
4. Проверки:
   - `eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationRuntimeState.ts resources/js/utils/simulationFormatters.ts resources/js/composables/useSimulationRecipes.ts resources/js/composables/useSimulationPolling.ts` — pass;
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 6)

1. Вынести `normalizeSimulationResult` и типы результатов в отдельный модуль `simulationResultParser`.
2. Сконсолидировать `open/close` lifecycle в `ZoneSimulationModal.vue` (подготовка формы/очистка состояния) в единый контроллер composable.
3. Повторить `lint + typecheck + guard` и зафиксировать финальную метрику сокращения `ZoneSimulationModal.vue`.

### Выполнено (S2, итерация 6)

1. Вынесен парсер результатов симуляции:
   - `resources/js/utils/simulationResultParser.ts` (`SimulationResults`, `SimulationPoint`, `normalizeSimulationResult`).
2. Сконсолидирован lifecycle модалки:
   - добавлен `resources/js/composables/useSimulationLifecycle.ts` (watch `isVisible` + unmount cleanup);
   - `ZoneSimulationModal.vue` переведен на `useSimulationLifecycle(...)` и `resetSimulationLifecycleState()` в `onSubmit`.
3. Компонент очищен от локального парсера/типов результата и дублирующих lifecycle-блоков.
4. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1226 -> 1189` строк.
5. Проверки:
   - `eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationLifecycle.ts resources/js/utils/simulationResultParser.ts` — pass;
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 7)

1. Вынести chart-конфигурацию (`chartPalette`, `chartOption`) в отдельный composable `useSimulationChart`.
2. Вынести применение `initialTelemetry` в отдельный helper/composable, чтобы убрать профильные watch-ветки из `ZoneSimulationModal.vue`.
3. Повторить `lint + typecheck + guard` и зафиксировать новую метрику.

### Выполнено (S2, итерация 7)

1. Вынесена chart-логика:
   - `resources/js/composables/useSimulationChart.ts` (`chartOption` + palette resolve).
2. Вынесена логика `initialTelemetry`:
   - `resources/js/composables/useSimulationInitialTelemetry.ts` (apply + internal watch).
3. `ZoneSimulationModal.vue` переведен на новые composable:
   - удалены локальные `resolveCssColor/chartPalette/chartOption`;
   - удалены локальные watch-ветки для `initialTelemetry`.
4. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1189 -> 1072` строк.
5. Проверки:
   - `eslint resources/js/Components/ZoneSimulationModal.vue resources/js/composables/useSimulationChart.ts resources/js/composables/useSimulationInitialTelemetry.ts resources/js/composables/useSimulationLifecycle.ts resources/js/utils/simulationResultParser.ts` — pass;
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass.

### Следующая итерация (S2, итерация 8)

1. Вынести форму запуска симуляции (`duration/recipe/initial_state/drift`) в отдельный компонент (`ZoneSimulationFormSection.vue`) с `v-model`/emit.
2. Оставить в `ZoneSimulationModal.vue` orchestration + результат/события/отчет.
3. Повторить `lint + typecheck + guard` и зафиксировать достижение целевого размера `< 900` строк.

### Выполнено (S2, итерация 8)

1. Вынесена форма запуска симуляции в отдельный компонент:
   - `resources/js/Components/ZoneSimulationFormFields.vue` (поля duration/recipe/initial_state/drift).
2. `ZoneSimulationModal.vue` переведен на новый компонент:
   - форма подключена через `v-model` (`form`, `recipeSearch`, drift-поля) и события (`markDriftTouched`, `applyAggressiveDrift`, `resetDriftValues`);
   - в модалке оставлена orchestration-логика + блоки прогресса/событий/отчета/результатов.
3. Метрика декомпозиции:
   - `ZoneSimulationModal.vue`: `1072 -> 749` строк (цель `< 900` достигнута).
4. Проверки:
   - `eslint resources/js/Components/ZoneSimulationModal.vue resources/js/Components/ZoneSimulationFormFields.vue` — pass;
   - `npm run typecheck` — pass.
5. Ограничения текущего рабочего дерева:
   - полный `eslint . --ext .ts,.tsx,.vue -f compact` возвращает warnings в нецелевых файлах (`Pages/Setup/Wizard.vue`, `Pages/Zones/Tabs/ZoneAutomationTab.vue`);
   - `check-file-size-guard.sh --working-tree` падает из-за нецелевых файлов, уже превышающих лимиты в текущем рабочем дереве (`Pages/Setup/Wizard.vue`, `Pages/Zones/Tabs/ZoneAutomationTab.vue`).

### Следующая итерация (S2, итерация 9)

1. Согласовать обработку нецелевых legacy-изменений в `Setup/Wizard.vue` и `ZoneAutomationTab.vue`:
   - либо отдельной задачей зачистить warnings/размер;
   - либо исключить из guard-линии до отдельного рефакторинга.
2. Перейти к следующему top-N крупному файлу из фронтенда/реалтайма (например `useWebSocket.ts` или `echoClient.ts`) с той же стратегией декомпозиции.

### Выполнено (S2, итерация 9)

1. Продолжена декомпозиция top-N файла `useWebSocket.ts`:
   - вынесен менеджер очереди отложенных подписок в `resources/js/ws/pendingSubscriptions.ts`;
   - из `useWebSocket.ts` удалены локальные реализации `createPendingSubscription` и `processPendingSubscriptions`;
   - `useWebSocket.ts` переведен на `pendingSubscriptionsManager.createPendingSubscription(...)` и `pendingSubscriptionsManager.processPendingSubscriptions()`.
2. Метрика декомпозиции:
   - `useWebSocket.ts`: `1146 -> 1008` строк.
   - Новый модуль: `pendingSubscriptions.ts` (191 строк).
3. Проверки:
   - `eslint resources/js/composables/useWebSocket.ts resources/js/ws/pendingSubscriptions.ts` — pass;
   - `npm run typecheck` — pass.
4. Ограничения текущего рабочего дерева:
   - полный `eslint . --ext .ts,.tsx,.vue -f compact` возвращает warnings в нецелевых файлах `Pages/Setup/Wizard.vue` и `Pages/Zones/Tabs/ZoneAutomationTab.vue`;
   - `check-file-size-guard.sh --working-tree` падает из-за тех же нецелевых файлов (превышение лимитов/дельты).

### Следующая итерация (S2, итерация 10)

1. Продолжить декомпозицию `useWebSocket.ts` до `< 900` строк:
   - вынести snapshot-sync (`fetch/apply snapshot`, reconnect sync) в модуль `ws/snapshotSync`.
2. Повторить `eslint(useWebSocket + новые ws/*) + typecheck`.
3. Зафиксировать новую метрику размера `useWebSocket.ts` и обновить план.

### Выполнено (S2, итерация 10)

1. Продолжена декомпозиция `useWebSocket.ts`:
   - вынесен snapshot-sync в `resources/js/ws/snapshotSync.ts`;
   - reconnect-path переведен на `snapshotSync.syncActiveZoneSnapshots()`;
   - API composable переведен на `fetchSnapshot: snapshotSync.fetchAndApplySnapshot`.
2. Дополнительно вынесен менеджер `resubscribe`:
   - `resources/js/ws/resubscribeManager.ts`;
   - cleanup переведен на `resubscribeManager.reset()`.
3. Метрика декомпозиции:
   - `useWebSocket.ts`: `1008 -> 894` строк.
4. Проверки:
   - `eslint resources/js/composables/useWebSocket.ts resources/js/ws/pendingSubscriptions.ts resources/js/ws/snapshotSync.ts resources/js/ws/resubscribeManager.ts` — pass;
   - `npm run typecheck` — pass.

### Следующая итерация (S2, итерация 11)

1. Вынести контроль канала (`ensure/detach/listeners/isDead/resubscribe`) из `useWebSocket.ts` в отдельный модуль.
2. Перевести `subscriptionLifecycle`, pending-manager и публичный `resubscribeAllChannels()` на новый модуль.
3. Зафиксировать новую метрику размера и повторить проверки в Docker.

### Выполнено (S2, итерация 11)

1. Вынесен менеджер управления каналами:
   - добавлен `resources/js/ws/channelControlManager.ts`;
   - из `useWebSocket.ts` удалены локальные реализации:
     - `getPusherChannel`,
     - `isChannelDead`,
     - `removeChannelListeners`,
     - `attachChannelListeners`,
     - `detachChannel`,
     - `ensureChannelControl`,
     - inline-реализация `resubscribeAllChannels`.
2. `useWebSocket.ts` переведен на `channelControlManager`:
   - lifecycle: `detachChannel`;
   - pending subscriptions: `isChannelDead`, `ensureChannelControl`;
   - cleanup: `removeChannelListeners`;
   - public API: `resubscribeAllChannels()` делегирует в manager.
3. Метрика декомпозиции:
   - `useWebSocket.ts`: `894 -> 643` строк.
   - Новый модуль: `channelControlManager.ts` (290 строк).
4. Проверки:
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel sh -lc './node_modules/.bin/eslint resources/js/composables/useWebSocket.ts resources/js/ws/channelControlManager.ts resources/js/ws/resubscribeManager.ts resources/js/ws/pendingSubscriptions.ts resources/js/ws/snapshotSync.ts'` — pass;
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel npm run typecheck` — pass;
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel sh -lc './node_modules/.bin/eslint . --ext .ts,.tsx,.vue -f compact'` — pass по errors, остаются legacy warnings в нецелевых файлах (`Pages/Setup/Wizard.vue`, `Pages/Zones/Tabs/ZoneAutomationTab.vue`);
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — fail из-за нецелевых крупных файлов (`Pages/Setup/Wizard.vue`, `Pages/Zones/Tabs/ZoneAutomationTab.vue`).

### Следующая итерация (S2, итерация 12)

1. Продолжить декомпозицию следующего top-N файла (`echoClient.ts`) с тем же паттерном: вынесение state/reconnect orchestration в `utils/echo*`/`ws/*`.
2. Отдельно зачистить legacy warnings в `Pages/Setup/Wizard.vue` и `Pages/Zones/Tabs/ZoneAutomationTab.vue`, чтобы вернуть `eslint` к `warnings = 0`.
3. После правок повторить `eslint + typecheck + file-size-guard` и зафиксировать baseline.

### Выполнено (S2, итерация 12)

1. Продолжена декомпозиция top-N файла `echoClient.ts`:
   - вынесен монолит connection-events/reconnect-callbacks в `resources/js/utils/echoConnectionEvents.ts`;
   - вынесена стратегия явного `connect()`-ретрая в `resources/js/utils/echoConnectStrategy.ts`;
   - вынесена reconciliation-логика (throttle + sync/full + event-dispatch) в `resources/js/utils/echoReconciliation.ts`.
2. `echoClient.ts` переведен на новые модули:
   - биндинг Pusher connection handlers через `bindEchoConnectionEvents(...)`;
   - connect retries через `attemptEchoConnect(...)`;
   - sync после reconnect через `reconciliationManager.performReconciliation()`.
3. Метрика декомпозиции:
   - `echoClient.ts`: `1063 -> 619` строк.
   - новые модули:
     - `echoConnectionEvents.ts` (348 строк),
     - `echoConnectStrategy.ts` (75 строк),
     - `echoReconciliation.ts` (85 строк).
4. Проверки:
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel sh -lc './node_modules/.bin/eslint resources/js/utils/echoClient.ts resources/js/utils/echoConnectionEvents.ts resources/js/utils/echoConnectStrategy.ts resources/js/utils/echoReconciliation.ts resources/js/utils/echoConfig.ts'` — pass;
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel npm run typecheck` — pass;
   - `docker compose -f backend/docker-compose.dev.yml run --rm laravel sh -lc './node_modules/.bin/eslint . --ext .ts,.tsx,.vue -f compact'` — pass по errors, остаются legacy warnings в нецелевых `Pages/Setup/Wizard.vue` и `Pages/Zones/Tabs/ZoneAutomationTab.vue`;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — fail из-за тех же нецелевых крупных файлов.

### Следующая итерация (S2, итерация 13)

1. Сконцентрироваться на legacy-блокере quality-gates:
   - убрать warnings в `Pages/Setup/Wizard.vue` и `Pages/Zones/Tabs/ZoneAutomationTab.vue` без ухудшения читаемости;
   - одновременно снизить размер этих файлов (через вынос секций/подкомпонентов), чтобы закрыть `file-size-guard`.
2. После правок повторить `eslint + typecheck + file-size-guard` и зафиксировать обновленный baseline.

### Выполнено (S2, итерация 13)

1. Закрыт legacy-блокер по двум top-N файлам:
   - `resources/js/Pages/Setup/Wizard.vue`;
   - `resources/js/Pages/Zones/Tabs/ZoneAutomationTab.vue`.
2. Проведена глубокая декомпозиция script-логики:
   - добавлен `resources/js/composables/useSetupWizard.ts` (вынесены данные шагов мастера, загрузка/создание сущностей, применение автоматики и запуск);
   - добавлен `resources/js/composables/useZoneAutomationTab.ts` (вынесены парсинг targets, синхронизация формы, payload/quick-actions).
3. Страницы переведены на orchestration-слой:
   - `Wizard.vue` и `ZoneAutomationTab.vue` теперь содержат компактный template + делегирование логики в composable.
4. Метрика размера:
   - `Wizard.vue`: `1524 -> 692` строк;
   - `ZoneAutomationTab.vue`: `1580 -> 460` строк.
5. Проверки:
   - `eslint resources/js/Pages/Setup/Wizard.vue resources/js/Pages/Zones/Tabs/ZoneAutomationTab.vue resources/js/composables/useSetupWizard.ts resources/js/composables/useZoneAutomationTab.ts` — pass;
   - `eslint . --ext .ts,.tsx,.vue -f compact` — pass (`errors = 0`, `warnings = 0`);
   - `npm run typecheck` — pass;
   - `backend/laravel/scripts/check-file-size-guard.sh --working-tree` — pass;
   - `npm run test -- resources/js/Pages/Setup/__tests__/Wizard.spec.ts resources/js/Pages/Zones/Tabs/__tests__/ZoneAutomationTab.spec.ts` — pass (`7/7`).

### Следующая итерация (S2, итерация 14)

1. Додекомпозировать `useZoneAutomationTab.ts` (862 строк) на доменные модули:
   - parser/apply-targets;
   - payload-builder/validation;
   - quick-actions runtime.
2. Повторить `eslint + typecheck + targeted tests` и зафиксировать снижение `useZoneAutomationTab.ts` до `< 700` строк.
