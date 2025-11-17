# Hot Reload в Development режиме

## Что настроено

### 1. PHP Hot Reload
- **Opcache отключен** в dev режиме (`php-dev.ini`)
- Изменения в PHP файлах применяются сразу без перезапуска
- Файлы монтируются через volume: `./laravel:/app`

### 2. Frontend Hot Reload (Vite)
- **Vite dev server** запущен через supervisor
- **HMR (Hot Module Replacement)** включен
- **File watching** настроен с polling для Docker на Windows
- Автоматическая перекомпиляция при изменении файлов в `resources/js/` и `resources/css/`

### 3. Автоматическое обновление
- Vite отслеживает изменения в:
  - Vue компонентах (`.vue`)
  - JavaScript файлах (`.js`, `.ts`)
  - CSS файлах (`.css`)
  - Конфигурационных файлах (`vite.config.js`)

## Как использовать

1. **Изменения в PHP коде**:
   - Просто сохраните файл
   - Изменения применятся сразу (opcache отключен)
   - Обновите страницу в браузере

2. **Изменения во Frontend коде**:
   - Сохраните файл
   - Vite автоматически перекомпилирует
   - Браузер обновится автоматически (HMR)

3. **Проверка работы**:
   - Откройте консоль браузера
   - Должны видеть сообщения от Vite HMR
   - При изменении файлов видите обновления в реальном времени

## Логи

- Vite лог: `docker exec backend-laravel-1 cat /tmp/vite.log`
- Reverb лог: `docker exec backend-laravel-1 cat /tmp/reverb.log`
- PHP opcache статус: `docker exec backend-laravel-1 php -r "echo 'opcache.enable: ' . (ini_get('opcache.enable') ? 'On' : 'Off');"`

## Устранение проблем

Если изменения не подхватываются:

1. Проверьте, что volume mount работает: `docker exec backend-laravel-1 ls -la /app/resources/js`
2. Проверьте статус Vite: `docker exec backend-laravel-1 cat /tmp/vite.log`
3. Перезапустите Vite: `docker exec backend-laravel-1 supervisorctl restart vite`
4. Проверьте opcache: должен быть `Off` в dev режиме

