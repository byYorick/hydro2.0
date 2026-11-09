# ANDROID_APP_ARCH.md
# Архитектура текущего Android-приложения

**Сверено с кодом:** 2026-11-07. Проект — [mobile/app/android](../../mobile/app/android/), Kotlin + Jetpack Compose. Runtime определяется подключёнными экранами и ViewModel, а не наличием заготовок классов.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Стек

[app/build.gradle.kts](../../mobile/app/android/app/build.gradle.kts) задаёт `minSdk=24`, `compileSdk=34`, `targetSdk=34`, Java 17 и flavors `dev/staging/prod`. UI использует Compose/Navigation, DI — Hilt, HTTP — Retrofit/OkHttp/Moshi. Room и DataStore присутствуют; токен хранится через `PreferencesDataSource`/`TokenAtRest` с Android Keystore cipher.

## Активный UI и слои

[MainActivity.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/MainActivity.kt) подключает login, server settings, greenhouses, zones, zone details, node details, alerts и provisioning. Точный состав — [ANDROID_APP_SCREENS.md](ANDROID_APP_SCREENS.md).

Основные операторские экраны из `ui/screens/OperatorScreens.kt` используют:

- `OverviewViewModel`, `ZoneListViewModel`, `OperatorAlertsViewModel` из `features/operator/ListViewModels.kt`;
- `ZoneOperatorViewModel`, `NodeOperatorViewModel` из `features/operator/DetailViewModels.kt`;
- [OperatorRepository.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/features/operator/OperatorRepository.kt), который вызывает Retrofit APIs и возвращает `Result`;
- `StateFlow` в памяти для состояния UI.

Room DAOs и старые repository/use-case/ViewModel цепочки остаются в коде, но текущие operator screens не читают все данные через Room. Универсальный offline-first flow для этих экранов не реализован. `TelemetryDao.getHistory(limit=1000)` ограничивает выборку, а не общий размер базы.

## Сеть и обновление данных

[BackendApis.kt](../../mobile/app/android/app/src/main/java/com/hydro/app/core/data/BackendApis.kt) и `features/auth/data/AuthApi.kt` определяют HTTP-контракт. `NetworkModule` добавляет Bearer token и `DynamicBaseUrlInterceptor`; выбранный сервер хранит `ServerEndpointStore` и меняет экран Settings.

Активные экраны обновляются REST polling: обзор теплиц — каждые 10 секунд, список зон и детали зоны/ноды — каждые 8 секунд, алерты — каждые 5 секунд; также доступно ручное обновление. Это интервалы задержки цикла, а не гарантия точной частоты запросов.

`RealtimeService.connectWebSocket` — отдельная заготовка, которая строит `/ws/{channel}`. Она не вызывается активными operator ViewModel и не реализует Reverb/Pusher subscribe/private-channel auth. Рабочая WebSocket-синхронизация и автоматический fallback между WS и polling не подтверждены этим классом. Прямого MQTT-клиента в app нет.

## Возможности и границы

- Просмотр теплиц, зон, нод, последних метрик и ACTIVE alerts.
- Подтверждение алерта через `PATCH /api/alerts/{id}/ack`.
- Принудительный полив через product command `FORCE_IRRIGATION`, перевод зоны в `manual`, перезапуск ноды и переключение relay channel.
- Полный редактор рецептов, lifecycle grow-cycle, history charts и push notifications не подключены в текущих operator screens.
- Provisioning экран существует, но его `/api/provision` несовместим с ESP32 portal `/wifi/connect`; рабочий браузерный путь описан в [ANDROID_APP_API_INTEGRATION.md](ANDROID_APP_API_INTEGRATION.md).

Изменения команд и прав всегда сверяются с Laravel: доступная кнопка не заменяет backend authorization. Архитектура не разрешает публиковать MQTT из приложения.
