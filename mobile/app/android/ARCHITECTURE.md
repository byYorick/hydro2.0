# Архитектура Android приложения Hydro 2.0

## Обзор

Приложение использует **Clean Architecture** с разделением на слои:
- **Presentation** - UI компоненты (Compose, ViewModels)
- **Domain** - Бизнес-логика (Use Cases, Domain Models, Errors)
- **Data** - Источники данных (Repositories, API, Database)

## Структура слоев

```
┌─────────────────────────────────────┐
│      Presentation Layer              │
│  (UI, ViewModels, Screens)          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       Domain Layer                  │
│  (Use Cases, Models, Errors)       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│        Data Layer                   │
│  (Repositories, API, Database)     │
└─────────────────────────────────────┘
```

## Domain Layer

### Use Cases

Use Cases инкапсулируют бизнес-логику приложения:

- **LoginUseCase** - Авторизация пользователя с валидацией
- **GetGreenhousesUseCase** - Получение списка теплиц
- **GetZonesUseCase** - Получение списка зон

### Domain Models

Модели домена не зависят от деталей реализации:
- `User`, `Greenhouse`, `Zone`, `Node`, `Alert`, `TelemetryLast`, etc.

### Error Handling

Унифицированная система обработки ошибок через `AppError`:
- `NetworkError` - Ошибки сети
- `ServerError` - Ошибки сервера
- `AuthError` - Ошибки авторизации
- `ValidationError` - Ошибки валидации
- `DatabaseError` - Ошибки базы данных

## Data Layer

### Repositories

Repositories абстрагируют источники данных:
- `AuthRepository` - Авторизация
- `GreenhousesRepository` - Теплицы
- `ZonesRepository` - Зоны
- `AlertsRepository` - Алерты
- `TelemetryRepository` - Телеметрия

### Data Sources

1. **Remote (API)** - Retrofit для сетевых запросов
2. **Local (Database)** - Room для локального кэширования
3. **Preferences** - DataStore для настроек и токенов

## Presentation Layer

### ViewModels

ViewModels используют Use Cases для получения данных:
- `LoginViewModel` - Экран входа
- `GreenhousesViewModel` - Список теплиц
- `ZonesViewModel` - Список зон

### UI Components

- **Compose Screens** - Экраны приложения
- **Compose Components** - Переиспользуемые UI компоненты

## Dependency Injection

Используется **Dagger Hilt** для управления зависимостями:

- `AppModule` - Общие зависимости
- `NetworkModule` - Сетевой слой
- `DatabaseModule` - База данных
- `BackendApisModule` - API интерфейсы

## Поток данных

```
User Action
    ↓
ViewModel
    ↓
Use Case
    ↓
Repository
    ↓
Data Source (API/Database)
    ↓
Flow/Result
    ↓
ViewModel
    ↓
UI Update
```

## Тестирование

- **Unit Tests** - ViewModels, Use Cases, Repositories
- **Integration Tests** - Room Database, API
- **UI Tests** - Compose screens

## Безопасность

- ProGuard для обфускации кода
- Certificate pinning (опционально)
- Правила резервного копирования
- DataStore для безопасного хранения токенов

## Производительность

- Room индексы для оптимизации запросов
- Flow с `SharingStarted.WhileSubscribed` для оптимизации подписок
- Кэширование данных в Room
- WebSocket с автоматическим переподключением

