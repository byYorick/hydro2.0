Мобильное приложение для hydro2.0.

## Структура

### Текущая реализация

- `app/android/` — Android-приложение на Kotlin
  - Архитектура: Clean Architecture (data, domain, presentation)
  - DI: Hilt
  - Networking: Retrofit
  - Realtime: WebSocket через Laravel Reverb
- `configs/` — конфигурации для разных окружений:
  - `env.dev.json`
  - `env.staging.json`
  - `env.prod.json`

### Структура Android-приложения

```
app/android/
├── app/
│   ├── src/main/java/com/hydro/app/
│   │   ├── core/          # Общие компоненты
│   │   │   ├── data/      # Репозитории, API клиенты
│   │   │   ├── domain/    # Модели, use cases
│   │   │   ├── di/        # Dependency Injection (Hilt)
│   │   │   ├── network/   # Сетевой слой
│   │   │   ├── prefs/     # DataStore
│   │   │   └── realtime/  # WebSocket сервис
│   │   ├── features/      # Функциональные модули
│   │   │   ├── auth/      # Авторизация
│   │   │   ├── greenhouses/ # Теплицы
│   │   │   ├── provisioning/ # Provisioning
│   │   │   ├── zones/     # Зоны
│   │   │   └── alerts/     # Алерты
│   │   ├── ui/            # UI компоненты
│   │   └── MainActivity.kt
│   └── build.gradle.kts
└── build.gradle.kts
```

## Документация

- Архитектура приложения: `doc_ai/12_ANDROID_APP/ANDROID_APP_ARCH.md`
- Экраны и UX: `doc_ai/12_ANDROID_APP/ANDROID_APP_SCREENS.md`
- Интеграция с API: `doc_ai/12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md`
- Структура проекта: `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- Backend API: `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`

## Примечание

Согласно документации, структура может включать также iOS-приложение в будущем.

