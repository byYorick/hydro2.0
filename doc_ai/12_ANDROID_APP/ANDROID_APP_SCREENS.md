# ANDROID_APP_SCREENS.md
# Подключённые экраны Android

**Сверено с кодом:** 2026-11-07. Источник маршрутов — [MainActivity.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/MainActivity.kt); операторский UI — [OperatorScreens.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/ui/screens/OperatorScreens.kt).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

| Route | Экран | Текущее поведение |
|---|---|---|
| `login` | `LoginScreen` | Email/password, получение API token; переход к теплицам после входа |
| `settings` | `ServerSettingsScreen` | Хост, порт, HTTPS и проверка подключения; доступен с login и из приложения |
| `greenhouses` | `GreenhousesScreen` / `OverviewViewModel` | Список теплиц, переход к зонам, алертам, настройкам и provisioning; polling 10 s |
| `zones/{greenhouseId}` | `ZonesScreen` / `ZoneListViewModel` | Список зон выбранной теплицы, polling 8 s и ручное обновление |
| `zone_details/{zoneId}` | `ZoneDetailsScreen` / `ZoneOperatorViewModel` | Метрики pH/EC/температуры, уровень, control mode/stage, связанные ноды; polling 8 s |
| `node/{nodeId}` | `NodeDetailsScreen` / `NodeOperatorViewModel` | Последняя telemetry, каналы реле, перезапуск; polling 8 s |
| `alerts` | `AlertsScreen` / `OperatorAlertsViewModel` | ACTIVE alerts, подтверждение, polling 5 s |
| `provisioning` | `ProvisioningScreen` | Форма и заготовка HTTP-настройки; несовместима с текущим ESP32 portal |

## Управление

Zone details отправляет `FORCE_IRRIGATION` с длительностью и позволяет перевести зону в ручной режим. Название «аварийно в ручной режим» означает вызов control-mode API; оно не является подтверждением физической остановки всех приводов.

Node details отправляет `restart` и `set_relay` для выбранного channel. Поддержку команды, binding, active lease и роль проверяет backend. Успешный HTTP-ответ не заменяет terminal device outcome.

Ack алерта вызывает `PATCH /api/alerts/{id}/ack`; backend переводит его в `RESOLVED`, после обновления он исчезает из списка ACTIVE. Статуса `acknowledged` в контракте нет.

## Границы текущих экранов

Welcome/onboarding, отдельный Alert Details, редактор recipe/grow-cycle, смена фазы и history charts не зарегистрированы в `MainActivity`. Наличие Compose-компонента или backend endpoint не означает, что сценарий подключён в приложении.

Provisioning не следует использовать как подтверждённый способ первой настройки. Текущий рабочий сценарий через браузер и причины несовместимости — [ANDROID_APP_API_INTEGRATION.md](ANDROID_APP_API_INTEGRATION.md#2-режим-provisioning-узлов-первая-настройка).
