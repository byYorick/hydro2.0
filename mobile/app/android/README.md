# Hydro Android App (Kotlin + Jetpack Compose)

Минимальный каркас Android‑приложения для Hydro 2.0.

## Стек
- Kotlin, Jetpack Compose, Navigation Compose
- Hilt (DI), Retrofit/OkHttp (сеть, пока не подключено)

## Старт
1. Откройте папку `mobile/app/android` в Android Studio.
2. Установите SDK 34.
3. Запустите конфигурацию `app`.

## Конфиг
- `BuildConfig.BACKEND_BASE_URL` — базовый URL backend (обновить в `app/build.gradle.kts`).
- `BuildConfig.WS_BASE_URL` — WebSocket‑URL для realtime.
- Соответствие API: см. `doc_ai/12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md`.

## Дальше
- Добавить слои `data/domain` и интеграцию REST (см. doc_ai/12_ANDROID_APP).
- Реализовать экраны по `ANDROID_APP_SCREENS.md`.


