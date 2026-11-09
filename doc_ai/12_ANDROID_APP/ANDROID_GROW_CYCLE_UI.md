# Android и управление grow cycle

**Сверено с кодом:** 2026-11-07. Этот документ описывает границу текущего Android UI и backend grow-cycle API. Отдельного grow-cycle wizard, редактора фаз и Retrofit `GrowCyclesApi` в приложении нет.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Что показывает приложение

`ZoneDetailsScreen` использует `ZoneOperatorViewModel` и `OperatorRepository.zoneDashboard`:

- читает зону, последние значения telemetry и связанные ноды;
- запрашивает `GET /api/zones/{id}/control-mode`;
- показывает `current_stage`, либо `workflow_phase`, и control mode;
- если control-mode API недоступен, показывает режим из zone DTO с сообщением об отсутствии живого состояния;
- обновляет данные REST polling с задержкой 8 секунд.

Стадия workflow автоматики не равна фазе рецепта. В текущем [BackendApis.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/core/data/BackendApis.kt) нет методов grow-cycle lifecycle; `core/domain/models.kt` не является полным DTO-контрактом этих операций.

Доступные действия — принудительный полив через `POST /api/zones/{id}/commands` (`type=FORCE_IRRIGATION`) и перевод зоны в `manual` через control-mode API. Они не создают новый grow cycle и не переключают фазу рецепта.

## Backend-контракт для клиентов

Laravel поддерживает grow-cycle API независимо от покрытия Android:

| Операция | Маршрут |
|---|---|
| Активный цикл зоны | `GET /api/zones/{id}/grow-cycle` |
| Создание цикла | `POST /api/zones/{id}/grow-cycles` |
| Жизненный цикл | `POST /api/grow-cycles/{id}/{start,pause,resume,harvest,abort}` |
| Фазы | `POST /api/grow-cycles/{id}/{set-phase,advance-phase}` |
| Смена ревизии | `POST /api/grow-cycles/{id}/change-recipe-revision` |

Request/response, статусы, роли и guards задают [API_SPEC_FRONTEND_BACKEND_FULL.md](../04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md) и `GrowCycleController`. Перечень URL не является описанием уже реализованного Android flow.

Источники агрономических targets — active grow-cycle phase и authority bundle; Android не пересчитывает PID и не управляет MQTT. Семантика crop day — [CROP_DAY_RUNTIME.md](../04_BACKEND_CORE/CROP_DAY_RUNTIME.md), режимов — [CONTROL_MODES_SPEC.md](../06_DOMAIN_ZONES_RECIPES/CONTROL_MODES_SPEC.md).

## Синхронизация

В Android нет активной Reverb/Pusher подписки на grow-cycle events. `RealtimeService` с URL `/ws/{channel}` не совместим с backend broadcasting-контрактом и не подтверждает такую интеграцию. Текущие экраны и сетевой слой описаны в [ANDROID_APP_ARCH.md](ANDROID_APP_ARCH.md) и [ANDROID_APP_API_INTEGRATION.md](ANDROID_APP_API_INTEGRATION.md).

При изменении Android lifecycle flow нужно сверять фактические DTO, HTTP-ответы, права и terminal outcomes с backend. Kotlin-примеры прежней версии этого документа не были подключённой реализацией.
