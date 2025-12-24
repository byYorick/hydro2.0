# Исправления в тестах UnassignedNodeErrorsTest

## Внесенные исправления

### 1. Исправлена работа с Carbon::now()
- **Проблема**: `$now->subHours(2)` изменяет оригинальный объект
- **Решение**: Использован `$now->copy()->subHours(2)` для создания копии

### 2. Улучшена проверка уникального ограничения
- **Проблема**: Строгая проверка на конкретное сообщение об ошибке может не работать в разных версиях PostgreSQL
- **Решение**: Добавлена более гибкая проверка, которая ищет любое из возможных сообщений об ошибке уникального ограничения

### 3. Исправлена обработка пустого списка нод в API
- **Проблема**: Если у зоны нет нод, `whereIn('node_id', [])` может вызвать ошибку SQL
- **Решение**: Добавлена проверка на пустой массив `$nodeIds` и ранний возврат пустого результата

## Запуск тестов

### Через Docker:
```bash
cd backend
docker compose -f docker-compose.dev.yml exec laravel php artisan test --filter UnassignedNodeErrorsTest
```

### Локально (если PHP установлен):
```bash
cd backend/laravel
php artisan test --filter UnassignedNodeErrorsTest
```

## Проверка миграций

### Выполнение миграций:
```bash
docker compose -f docker-compose.dev.yml exec laravel php artisan migrate
```

### Проверка структуры таблицы (SQL):
```bash
docker compose -f docker-compose.dev.yml exec db psql -U hydro -d hydro_dev -f /path/to/check_migration.sql
```

Или через Laravel:
```bash
docker compose -f docker-compose.dev.yml exec laravel php artisan tinker
>>> DB::select("SELECT column_name FROM information_schema.columns WHERE table_name = 'unassigned_node_errors'");
```

## Тестовые сценарии

Все тесты проверяют:

1. ✅ Существование таблицы и правильность структуры
2. ✅ Вставку ошибок
3. ✅ Уникальное ограничение на (hardware_id, COALESCE(error_code, ''))
4. ✅ Авторизацию API endpoints
5. ✅ Получение ошибок для зоны
6. ✅ Привязку ошибок к нодам при регистрации
7. ✅ Создание alerts из unassigned errors
8. ✅ Фильтрацию по severity
9. ✅ Обработку NULL в error_code

