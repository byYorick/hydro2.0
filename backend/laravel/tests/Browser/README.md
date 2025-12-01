# Browser Tests (Laravel Dusk)

## Обзор

Browser тесты используют Laravel Dusk для тестирования реального взаимодействия пользователя с приложением через браузер.

## Структура тестов

### AuthenticationTest.php
- `test_user_can_login_and_redirect_to_dashboard()` - тест входа пользователя
- `test_unauthenticated_user_redirected_to_login()` - тест редиректа неавторизованных
- `test_user_can_logout()` - тест выхода пользователя

### ZonesTest.php
- `test_zones_list_page_loads()` - тест загрузки списка зон
- `test_zone_detail_page_loads()` - тест загрузки детальной страницы зоны
- `test_navigation_from_dashboard_to_zones()` - тест навигации между страницами

### DevicesTest.php
- `test_devices_list_page_loads()` - тест загрузки списка устройств
- `test_device_detail_page_loads()` - тест загрузки детальной страницы устройства

### RecipesTest.php
- `test_recipes_list_page_loads()` - тест загрузки списка рецептов
- `test_recipe_detail_page_loads()` - тест загрузки детальной страницы рецепта
- `test_recipe_create_page_loads()` - тест загрузки страницы создания рецепта

### ProfileTest.php
- `test_profile_page_loads()` - тест загрузки страницы профиля
- `test_profile_information_can_be_updated()` - тест обновления профиля

### NavigationTest.php
- `test_user_can_navigate_between_main_pages()` - тест навигации между основными страницами
- `test_dashboard_shows_statistics()` - тест отображения статистики на дашборде

### ExampleTest.php
- `test_dashboard_after_login()` - базовый тест дашборда после входа

## Запуск тестов

### Все browser тесты
```bash
docker compose -f backend/docker-compose.dev.yml run --rm \
  -e APP_ENV=testing \
  -e APP_URL=http://127.0.0.1:8000 \
  -e DUSK_CHROME_PATH=/usr/bin/chromium \
  laravel bash -lc "cd /app && php artisan migrate --force && php artisan serve --host=127.0.0.1 --port=8000 > storage/logs/serve-dusk.log 2>&1 & SERVER_PID=\$!; sleep 5; php artisan dusk --env=dusk --without-tty; STATUS=\$?; kill \$SERVER_PID || true; exit \$STATUS"
```

### Конкретный тест
```bash
php artisan dusk --filter=test_user_can_login
```

### Все тесты в файле
```bash
php artisan dusk tests/Browser/AuthenticationTest.php
```

## Требования

- Chromium или Chrome браузер
- Chromedriver
- Laravel dev сервер должен быть запущен (автоматически при запуске через artisan dusk)

## Особенности

- Тесты используют `loginAs()` для быстрой аутентификации
- Проверяют Inertia компоненты через `document.getElementById("app").dataset.page`
- Используют `waitFor()` для ожидания загрузки элементов
- Проверяют пути через `assertPathIs()`

## Добавление новых тестов

1. Создайте новый файл в `tests/Browser/`
2. Наследуйтесь от `Tests\DuskTestCase`
3. Используйте `$this->browse()` для тестирования
4. Используйте фабрики для создания тестовых данных
5. Проверяйте Inertia компоненты через JavaScript

