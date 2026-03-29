# AE3 Error Code Canonicalization Plan

**Версия:** 1.0  
**Дата:** 2026-03-29  
**Статус:** Draft  

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Перевести `automation-engine`, Laravel API и frontend на каноническую модель:

- runtime и backend передают наружу не сырые текстовые ошибки, а `error_code`;
- человекочитаемые описания, заголовки и рекомендации живут в едином каталоге кодов;
- frontend отображает только локализованные описания по коду;
- английские raw-message остаются только как временный compatibility fallback на переходный период.

## Контекст и проблема

Сейчас система частично канонизирована, но остаётся split-brain между кодами и строками:

1. Для алертов уже существует каталог `backend/alert_codes.json`.
2. Для ошибок уже существует каталог `backend/error_codes.json`, но он покрывает только часть runtime/API кейсов.
3. AE3 всё ещё использует raw English messages как часть business semantics:
   - `SnapshotBuildError(f"Zone {zone_id} has no online actuator channels")`
   - `SnapshotBuildError(f"Zone {zone_id} has no active grow_cycle")`
   - и другие `SnapshotBuildError(...)` в `zone_snapshot_read_model.py`
4. В `execute_task.py` есть token-based логика:
   - `SNAPSHOT_NO_ONLINE_ACTUATORS_TOKEN = "has no online actuator channels"`
5. Laravel и frontend уже пытаются локализовать часть сообщений, но делают это через:
   - каталог кодов;
   - exact-map raw-message translations;
   - fallback по тексту.

Это создаёт три класса дефектов:

1. Одинаковая ошибка может приходить то по `error_code`, то по сырой строке.
2. Русская локализация зависит от точного совпадения английского текста.
3. Automation не имеет стабильного машинного контракта для части fail-closed сценариев.

## Целевое состояние

### 1. Единый словарь кодов

Нужны два канонических каталога:

1. `backend/error_codes.json`
   Для ошибок выполнения, API-ошибок, runtime degradations, fail-closed состояний, command failures.
2. `backend/alert_codes.json`
   Для alert lifecycle, severity/category/recommendation и UI деталей алерта.

Laravel mirror-файлы допускаются только как производные копии для runtime/frontend сборки, но source of truth должен быть один на каталог.

### 2. Runtime contract

Во всех automation runtime path:

- terminal failure должен иметь стабильный `error_code`;
- `error_message` должен быть опциональным debug-context, а не носителем бизнес-смысла;
- internal branching в AE3 не должен зависеть от substring raw-message.

### 3. Frontend contract

Frontend должен рендерить:

- `title`
- `message`
- при необходимости `recommendation`

по каноническому коду, а не по сырому тексту.

Raw `error_message` на UI допускается только как временный fallback для legacy записей.

## Границы и инварианты

### В scope

- `backend/services/automation-engine/**`
- `backend/laravel/**`
- `backend/error_codes.json`
- `backend/alert_codes.json`
- frontend composables/utilities, использующие `errorCatalog`
- API/presenter слои, которые отдают `human_error_message`

### Не в scope

- изменение MQTT error payload от firmware, если это не требуется отдельным решением;
- redesign alert lifecycle;
- изменение DB-схемы без явной необходимости.

### Инварианты

- protected pipeline не меняется;
- `AlertService` остаётся owner lifecycle алертов;
- frontend не должен знать доменную логику AE3, только коды и каталог;
- английские строки не являются контрактом.

## Аудит текущих проблемных зон

### A. AE3 snapshot/read-model ошибки

Проблема:

- `zone_snapshot_read_model.py` генерирует множество `SnapshotBuildError` через сырой текст.
- `execute_task.py` интерпретирует часть этих ошибок по substring.

Нужно:

- заменить string-only ошибки на code-first модель;
- для `SnapshotBuildError` ввести обязательный `code` и опциональный `message`;
- убрать token-ветвление по `"has no online actuator channels"`.

### B. AE3 terminal errors

Проблема:

- часть `TaskExecutionError` уже кодовая;
- часть исключений и fail-closed веток всё ещё формируют только текст;
- каталог покрывает не все runtime причины.

Нужно:

- составить полную таблицу terminal/non-terminal кодов AE3;
- выровнять коды между `execute_task`, `workflow_router`, handlers, startup recovery и state API.

### C. Laravel presentation layer

Проблема:

- `ErrorCodeCatalogService` содержит raw translation map;
- frontend `errorCatalog.ts` дублирует ту же идею;
- часть описаний уже идёт по коду, часть по сообщению.

Нужно:

- оставить raw-message translation только как временный compatibility слой;
- убрать дублирование источников истины;
- гарантировать, что любой код из automation имеет русское описание в каталоге.

### D. Frontend UI

Проблема:

- UI всё ещё может показать английский `message`, если код отсутствует в каталоге;
- часть страниц использует общий resolver, часть работает с API полями напрямую.

Нужно:

- унифицировать все экраны через один resolver;
- запретить прямой рендер сырых англоязычных runtime сообщений в normal path.

## Каноническая таблица кодов

Нужна нормализованная таблица с такими колонками:

1. `code`
2. `domain`
   - `api`
   - `command`
   - `ae3_snapshot`
   - `ae3_execution`
   - `ae3_recovery`
   - `infra`
   - `node`
3. `kind`
   - `error`
   - `alert`
4. `title_ru`
5. `message_ru`
6. `recommendation_ru`
7. `http_status`
   - если применимо
8. `ui_surface`
   - `zone_state`
   - `command_status`
   - `zone_alert_modal`
   - `toast`
   - `scheduler`
9. `source_module`
10. `legacy_raw_messages`
11. `notes`

Эта таблица сначала собирается как рабочий аудит-документ, потом переносится в JSON-каталоги и тесты.

## План реализации

### Фаза 0. Аудит и freeze словаря

Цель:

- зафиксировать полный перечень существующих кодов и сырых сообщений до рефакторинга.

Шаги:

1. Собрать все `error_code` из:
   - AE3 use cases
   - DTO/state presenters
   - Laravel controllers/services
   - frontend tests
2. Собрать все raw-message исключения из:
   - `SnapshotBuildError`
   - `TaskExecutionError`
   - `PlannerConfigurationError`
   - legacy exact-map translations
3. Свести в markdown-таблицу:
   - уже покрыто каталогом
   - отсутствует в каталоге
   - raw-only
   - dead/legacy

Definition of done:

- есть полная таблица соответствий `source -> code -> catalog entry -> UI surface`.

### Фаза 1. Нормализовать каталог ошибок

Цель:

- сделать `backend/error_codes.json` полным и достаточным для automation/API/UI.

Шаги:

1. Добавить недостающие AE3 коды, как минимум для:
   - snapshot gaps
   - invalid bundle/config
   - no online actuators
   - missing grow cycle / phase / bundle
   - empty command plans
   - fail-safe shutdown/finalize/runtime failures
2. Выровнять naming policy:
   - только `snake_case`
   - без смешения human terms и transport terms
3. Определить правила:
   - когда код переиспользуется;
   - когда создаётся новый код;
   - когда это alert, а не error.

Definition of done:

- каждый код из runtime имеет запись в каталоге;
- у каждой записи есть русский `title` и `message`;
- для UI-критичных кодов есть `recommendation`.

### Фаза 2. Перевести AE3 на code-first исключения

Цель:

- исключения и terminal state AE3 больше не зависят от сырого текста.

Шаги:

1. Расширить доменные исключения:
   - `SnapshotBuildError`
   - при необходимости `PlannerConfigurationError`
   так, чтобы код был обязательным полем.
2. Заменить raw `raise SnapshotBuildError("...")` на code-first вызовы:
   - пример: `SnapshotBuildError(code="ae3_snapshot_no_online_actuator_channels", message="...debug...")`
3. В `execute_task.py` убрать substring-token ветвление и перейти на `error.code`.
4. Привести `fail_closed` path к правилу:
   - в state/API идёт стабильный `error_code`;
   - raw message не определяет поведение.

Definition of done:

- в AE3 нет runtime business logic, завязанной на английский raw text;
- snapshot-кейсы ветвятся по коду.

### Фаза 3. Выровнять Laravel presentation contract

Цель:

- backend API отдаёт человеку русское описание по коду.

Шаги:

1. Оставить `ErrorCodeCatalogService` единым presenter-слоем для ошибок.
2. Перевести его на правило:
   - сначала `error_code`;
   - затем known legacy raw-message mapping;
   - затем safe fallback.
3. Удалить дублирующие расхождения между PHP и frontend resolver.
4. Если возможно, отдать на frontend уже готовые поля:
   - `human_error_title`
   - `human_error_message`
   - `human_error_recommendation`

Definition of done:

- любое API место с automation error имеет стабильный human-readable русскоязычный ответ.

### Фаза 4. Упростить frontend до code-driven rendering

Цель:

- UI не локализует хаотично и не знает английских текстов automation.

Шаги:

1. Оставить один общий resolver для ошибок.
2. Все automation экраны перевести на него:
   - zone details
   - alerts
   - scheduler
   - dashboard
   - command status
3. Запретить прямой вывод `error_message`, кроме explicit legacy fallback path.
4. Для alert details использовать каталог алертов:
   - `title`
   - `description`
   - `recommendation`

Definition of done:

- пользователь не видит английские automation/runtime ошибки в normal path.

### Фаза 5. Cleanup legacy fallback

Цель:

- raw English strings перестают быть частью контракта.

Шаги:

1. Почистить временные raw translation maps после cutover.
2. Оставить только ограниченный fallback для старых исторических записей.
3. Добавить guard-тесты, запрещающие новые raw-only ошибки в AE3 critical path.

Definition of done:

- новые runtime ошибки обязаны иметь код и каталог;
- raw-message-only кейсы считаются regression.

## Тестовая стратегия

### Unit

1. AE3:
   - `SnapshotBuildError` carries canonical code
   - `execute_task` ветвится по коду, а не по сообщению
2. Laravel:
   - `ErrorCodeCatalogService` правильно резолвит `code -> ru text`
   - legacy raw-message mapping работает только как fallback
3. Frontend:
   - resolver выбирает каталог по коду
   - английский raw text не попадает в UI, если код известен

### Integration

1. AE3 task failure -> `error_code` сохраняется в task state
2. Laravel state/command endpoints -> возвращают `human_error_message`
3. Alerts API -> используют `alert_codes.json` для modal/details

### E2E

1. Сценарий с AE3 failure показывает русский текст на странице зоны
2. Сценарий command timeout показывает русский текст в UI
3. Сценарий alert details показывает русский title/description/recommendation

## Риски

1. Один и тот же raw-message может сегодня использоваться в тестах и implicit branching.
2. Переименование кодов сломает исторические данные и assertions, если не сделать mapping.
3. Если смешать `error` и `alert` taxonomy, каталог снова расползётся.

## Rollout

1. Сначала расширить каталог и presenters без изменения runtime semantics.
2. Затем перевести AE3 исключения на code-first.
3. Затем перевести UI на strict code-driven rendering.
4. Затем удалить raw-message business logic и старые fallback maps.

## Открытые вопросы

1. Нужен ли отдельный third catalog для firmware/node error codes, или текущий `error_codes.json` должен охватить и AE3, и firmware, и API?
2. Исторические записи `commands` / `ae_tasks` без канонического `error_code` нужно:
   - оставить как legacy,
   - мигрировать best-effort,
   - или нормализовать только новые записи?
3. На UI нужно показывать только `message`, или везде выводить тройку:
   - `title`
   - `message`
   - `recommendation`
4. Для alert catalog подтверждаем канон:
   - `alert_codes.json` остаётся отдельным от `error_codes.json`,
   - а не объединяется в общий universal catalog?
5. Для AE3 snapshot/config errors вы хотите granular codes на каждый кейс:
   - `no_active_grow_cycle`
   - `missing_current_phase`
   - `invalid_bundle_config`
   или допустим более агрегированный класс `ae3_snapshot_invalid_runtime_state` с деталями в debug message?

