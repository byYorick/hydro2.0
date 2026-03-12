# Настройка тестового окружения

## Конфигурация

Тестовое окружение настроено в `phpunit.xml`:
- `APP_ENV=testing`
- `DB_CONNECTION=pgsql`
- `DB_DATABASE=hydro_test`
- `BROADCAST_DRIVER=log` (отключен broadcasting для тестов)
- `CACHE_STORE=array`
- `SESSION_DRIVER=array`
- `QUEUE_CONNECTION=sync`

## Запуск тестов

### Все тесты
```bash
php artisan test
```

### Только Unit тесты
```bash
php artisan test --testsuite=Unit
```

### Только Feature тесты
```bash
php artisan test --testsuite=Feature
```

### Конкретный тест
```bash
php artisan test --filter=ZonesTest
```

## Статус тестов

### ✅ Проходящие тесты (65 тестов)

#### Unit тесты (28 тестов)
- `ZoneServiceTest` - 12 тестов
- `RecipeServiceTest` - 7 тестов
- `NodeServiceTest` - 4 теста
- `AlertServiceTest` - 3 теста
- `ExampleTest` - 1 тест

#### Feature тесты (41 тест)
- `ZonesTest` - 11 тестов ✅
- `RecipesTest` - 10 тестов ✅
- `NodesTest` - 8 тестов ✅
- `AlertsTest` - 7 тестов ✅
- `CommandsTest` - 2 теста ✅
- `TelemetryTest` - 2 теста ✅
- `AuthTest` - 1 тест ✅

### ⚠️ Тесты, требующие веб-интерфейс (17 тестов)

Эти тесты относятся к стандартному Laravel Breeze и требуют настройки веб-маршрутов:
- `Auth\AuthenticationTest` - 2 теста (login/logout через веб)
- `Auth\PasswordConfirmationTest` - 2 теста
- `Auth\PasswordResetTest` - 3 теста
- `Auth\PasswordUpdateTest` - 2 теста
- `Auth\RegistrationTest` - 1 тест
- `ProfileTest` - 5 тестов (требует `/profile` маршрут)
- `ExampleTest` - 1 тест (может быть исправлен)

Эти тесты можно исправить, добавив соответствующие маршруты в `routes/web.php` или пометив их как `@skip`.

## Настройка базы данных для тестов

Тесты используют отдельную базу данных `hydro_test`. Убедитесь, что она создана:

```bash
# В контейнере Laravel
php artisan db:create hydro_test
```

Или используйте существующую базу с `RefreshDatabase` trait, который автоматически создает и очищает схему.

## Фабрики

Все необходимые фабрики созданы:
- `ZoneFactory`
- `GreenhouseFactory`
- `RecipeFactory`
- `RecipePhaseFactory`
- `ZoneRecipeInstanceFactory`
- `DeviceNodeFactory`
- `AlertFactory`
- `UserFactory` (стандартная Laravel)

## Особенности

1. **Broadcasting отключен** - используется `Event::fake()` в `TestCase`, чтобы не зависеть от Reverb
2. **Notifications отключены** - используется `Notification::fake()`
3. **База данных** - используется `RefreshDatabase` trait для изоляции тестов

