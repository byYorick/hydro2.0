# E2E / Browser Testing

## Playwright smoke suite

- Конфиг: `playwright.config.ts` (web-сервер `php artisan serve --host=127.0.0.1 --port=8000`)
- Тесты: `tests/E2E/*.spec.ts`
  - `dashboard.smoke.spec.ts` — проверяет логин под `admin@example.com / password`, наличие WebSocket-индикаторов и доступ к `/zones`.
  - `pid-config.spec.ts` помечен `describe.skip` до появления стабильных фикстур Automation Engine.
- Скрипты:
- `npm run e2e` — запускает `playwright test` (ожидает, что браузеры и ассеты уже установлены/собраны).
- `npm run e2e:ci` — последовательно выполняет `npm run build`, устанавливает браузеры (`playwright install --with-deps`) и затем запускает тесты. Используйте в CI/одноразовых контейнерах.

## Laravel Dusk

Dusk установлен (`composer require --dev laravel/dusk`, `php artisan dusk:install`). Для локального запуска нужен Chromium/Chrome. В dev-контейнере можно установить `chromium chromium-driver` или использовать внешний Selenium (`DUSK_DRIVER_URL=http://selenium:4444/wd/hub`, `DUSK_CHROME_PATH=/usr/bin/chromium`). Команда запуска:

```bash
php artisan dusk --env=dusk
```

В контейнере без предустановленного браузера тесты завершатся ошибкой `cannot find Chrome binary`.

