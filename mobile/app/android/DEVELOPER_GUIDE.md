# Руководство для разработчиков - Hydro 2.0 Android

## Настройка окружения

### Требования

- Android Studio Hedgehog или новее
- JDK 17
- Android SDK 34
- Gradle 8.0+

### Установка

1. Клонируйте репозиторий
2. Откройте проект в Android Studio
3. Дождитесь синхронизации Gradle
4. Выберите flavor (dev/staging/prod) в Build Variants

## Структура проекта

```
app/src/main/java/com/hydro/app/
├── core/                    # Общие компоненты
│   ├── config/             # Конфигурация
│   ├── data/               # Repositories, API
│   ├── database/           # Room entities, DAOs
│   ├── di/                 # Dependency Injection
│   ├── domain/             # Domain models, Use Cases
│   ├── network/            # Network utilities
│   ├── prefs/              # DataStore
│   └── realtime/           # WebSocket service
├── features/                # Функциональные модули
│   ├── auth/               # Авторизация
│   ├── greenhouses/        # Теплицы
│   ├── zones/              # Зоны
│   └── alerts/             # Алерты
└── ui/                      # UI компоненты
    ├── components/          # Переиспользуемые компоненты
    └── screens/            # Экраны приложения
```

## Разработка новой функции

### 1. Создайте Domain Model

```kotlin
// core/domain/models.kt
@JsonClass(generateAdapter = true)
data class MyEntity(
    val id: Int,
    val name: String
)
```

### 2. Создайте Use Case

```kotlin
// core/domain/usecase/GetMyEntityUseCase.kt
class GetMyEntityUseCase @Inject constructor(
    private val repository: MyEntityRepository
) {
    suspend fun invoke(id: Int): AppResult<MyEntity> {
        // Бизнес-логика
    }
}
```

### 3. Создайте Repository

```kotlin
// core/data/Repositories.kt
@Singleton
class MyEntityRepository @Inject constructor(
    private val api: MyEntityApi,
    private val db: HydroDatabase
) {
    fun getAll(): Flow<List<MyEntity>> {
        // Реализация
    }
}
```

### 4. Создайте ViewModel

```kotlin
// features/myfeature/MyEntityViewModel.kt
@HiltViewModel
class MyEntityViewModel @Inject constructor(
    private val getMyEntityUseCase: GetMyEntityUseCase
) : ViewModel() {
    val state: StateFlow<List<MyEntity>> = 
        getMyEntityUseCase.invoke()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
}
```

### 5. Создайте UI

```kotlin
// ui/screens/MyEntityScreen.kt
@Composable
fun MyEntityScreen(
    viewModel: MyEntityViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsState()
    // UI код
}
```

## Тестирование

### Unit тесты

```kotlin
@Test
fun `my test case`() = runTest {
    // Arrange
    // Act
    // Assert
}
```

### Запуск тестов

```bash
./gradlew test              # Unit тесты
./gradlew connectedAndroidTest  # Интеграционные тесты
```

## Сборка

### Debug

```bash
./gradlew assembleDevDebug
```

### Release

```bash
./gradlew assembleProdRelease
```

## Конфигурация

Конфигурационные файлы находятся в `assets/configs/`:
- `env.dev.json` - Development
- `env.staging.json` - Staging
- `env.prod.json` - Production

## Лучшие практики

1. **Всегда используйте Use Cases** - не вызывайте Repository напрямую из ViewModel
2. **Используйте Flow для реактивных данных** - StateFlow для состояния UI
3. **Обрабатывайте ошибки** - используйте AppError для унифицированной обработки
4. **Добавляйте KDoc комментарии** - документируйте публичные API
5. **Пишите тесты** - покрывайте Use Cases и ViewModels тестами
6. **Следуйте Clean Architecture** - разделяйте слои правильно

## Отладка

### Логирование

В debug режиме включено подробное логирование:
- HTTP запросы/ответы
- WebSocket события
- Ошибки

### Инструменты

- Android Studio Profiler - для анализа производительности
- Layout Inspector - для анализа UI
- Database Inspector - для просмотра Room database

## Troubleshooting

### Проблемы с зависимостями

```bash
./gradlew clean
./gradlew --refresh-dependencies
```

### Проблемы с Room

Убедитесь, что версия database обновлена при изменении схемы.

### Проблемы с Hilt

Очистите build кэш:
```bash
./gradlew clean
rm -rf .gradle
```

## Дополнительные ресурсы

- [Android Developer Documentation](https://developer.android.com)
- [Jetpack Compose](https://developer.android.com/jetpack/compose)
- [Room Database](https://developer.android.com/training/data-storage/room)
- [Dagger Hilt](https://dagger.dev/hilt/)

