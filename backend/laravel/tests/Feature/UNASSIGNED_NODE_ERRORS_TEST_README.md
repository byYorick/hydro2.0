# Тесты для Unassigned Node Errors

## Описание

Тесты проверяют функциональность системы обработки ошибок от незарегистрированных/непривязанных узлов.

## Запуск тестов

### Через Docker:
```bash
cd backend
docker compose exec laravel php artisan test --filter UnassignedNodeErrorsTest
```

### Локально (если PHP установлен):
```bash
cd backend/laravel
php artisan test --filter UnassignedNodeErrorsTest
```

## Выполнение миграций

### Через Docker:
```bash
cd backend
docker compose exec laravel php artisan migrate
```

### Локально:
```bash
cd backend/laravel
php artisan migrate
```

## Тестовые сценарии

1. **test_unassigned_errors_table_exists** - Проверка структуры таблицы
2. **test_can_insert_unassigned_error** - Проверка вставки ошибки
3. **test_unique_constraint_on_hardware_id_and_code** - Проверка уникального ограничения
4. **test_get_zone_unassigned_errors_requires_auth** - Проверка авторизации API
5. **test_get_zone_unassigned_errors** - Проверка получения ошибок для зоны
6. **test_unassigned_errors_attached_to_node_on_registration** - Проверка привязки ошибок при регистрации ноды
7. **test_unassigned_errors_filtered_by_severity** - Проверка фильтрации по severity
8. **test_unassigned_errors_with_null_error_code** - Проверка обработки NULL в error_code

