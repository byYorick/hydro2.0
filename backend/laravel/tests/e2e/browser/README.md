# Браузерные тесты Playwright для фронтенда

Этот набор тестов предназначен для автоматического тестирования веб-интерфейса (Vue 3 + Inertia) с помощью Playwright. Тесты могут выполняться автономно ИИ-агентом для регрессионного тестирования UI.

## Структура

```
tests/e2e/browser/
├── playwright.config.ts      # Конфигурация Playwright
├── specs/                     # Тестовые сценарии
│   ├── 01-login.spec.ts
│   ├── 02-dashboard.spec.ts
│   ├── 03-zone-detail.spec.ts
│   ├── 04-cycle-control.spec.ts
│   ├── 05-commands.spec.ts
│   ├── 06-grow-cycle.spec.ts
│   ├── 07-alerts.spec.ts
│   ├── 08-bindings.spec.ts
│   └── 09-ws-degradation.spec.ts
├── helpers/                   # Вспомогательные функции
│   └── api.ts                 # API хелперы для создания/удаления тестовых данных
├── fixtures/                  # Playwright фикстуры
│   └── test-data.ts           # Фикстуры для подготовки тестовых данных
├── types/                     # TypeScript типы
│   └── index.ts
├── constants.ts               # Константы для data-testid
└── playwright/
    └── .auth/
        └── setup.ts           # Автоматическая авторизация
```

## Требования

1. **Окружение**: Laravel должен быть запущен через `docker-compose -f tests/e2e/docker-compose.e2e.yml up -d`
   - Laravel на `http://localhost:8081`
   - WebSocket Reverb на `ws://localhost:6002/app/local`
   - MQTT на порту 1884
   - PostgreSQL на порту 5433

2. **Пользователь**: Используется сидированный админ
   - По умолчанию: `admin@hydro.local` / `password`
   - Можно переопределить через переменные окружения:
     - `E2E_AUTH_EMAIL` - email для авторизации
     - `E2E_AUTH_PASSWORD` - пароль для авторизации
     - `LARAVEL_URL` - URL Laravel приложения (по умолчанию `http://localhost:8081`)

3. **Зависимости**: Playwright должен быть установлен
   ```bash
   cd backend/laravel
   npm install
   npx playwright install chromium
   ```

## Запуск тестов

### Из директории backend/laravel:

```bash
# Запуск всех тестов
npm run e2e:browser

# Запуск с UI (интерактивный режим)
npm run e2e:browser:ui

# Запуск конкретного теста
npx playwright test --config=../../tests/e2e/browser/playwright.config.ts specs/01-login.spec.ts

# Запуск в headless режиме
npx playwright test --config=../../tests/e2e/browser/playwright.config.ts --headed=false
```

### Из директории tests/e2e/browser:

```bash
# Запуск всех тестов
npx playwright test

# Запуск с UI
npx playwright test --ui

# Запуск конкретного теста
npx playwright test specs/01-login.spec.ts
```

## Тестовые сценарии

### 1. Login/Logout (`01-login.spec.ts`)
- Успешный вход и редирект на Dashboard
- Отображение ошибки при неверных учетных данных
- Выход из системы

### 2. Dashboard Overview (`02-dashboard.spec.ts`)
- Отображение карточки количества зон
- Отображение карточек зон со статусами
- Отображение карточки алертов
- Отображение панели событий
- Фильтрация событий по типу
- Переход на детальную страницу зоны по клику на карточку

### 3. Zone Detail (`03-zone-detail.spec.ts`)
- Загрузка детальной страницы зоны
- Отображение snapshot (наличие last_event_id, telemetry-блоков)
- Отображение списка событий
- Появление новых событий после действий

### 4. Cycle Control (`04-cycle-control.spec.ts`)
- Запуск зоны (статус → RUNNING)
- Пауза зоны (статус → PAUSED)
- Возобновление зоны (статус → RUNNING)
- Сбор урожая (статус → HARVESTED)
- Появление zone_events/уведомлений в UI

### 5. Commands (`05-commands.spec.ts`)
- Отправка команды узлу
- Проверка статусов SENT/ACK/DONE/NO_EFFECT в UI
- Обновление без перезагрузки (WebSocket)
- Отображение ошибки при некорректном канале

### 6. Grow Cycle Recipe (`06-grow-cycle.spec.ts`)
- Создание рецепта (имя + описание)
- Привязка рецепта к зоне
- Проверка статуса PLANNED и наличия текущей фазы
- Отображение фаз/таймлайна
- Проверка процентов прогресса

### 7. Alerts (`07-alerts.spec.ts`)
- Фильтрация по статусу (ACTIVE/ACK/CLEARED)
- Фильтрация по зоне
- Отображение строк алертов
- Подтверждение алерта (смена статуса)

### 8. Bindings (`08-bindings.spec.ts`)
- Создание binding (role -> node/channel) через UI
- Проверка отображения резолва в UI
- Проверка отправки команды по роли на правильный node/channel

### 9. WS Degradation (`09-ws-degradation.spec.ts`)
- Проверка индикатора подключения WS
- Отключение сети и проверка отображения потери соединения
- Включение сети и проверка авто-переподключения
- Появление событий после reconnect

## Подготовка данных

Тесты автоматически создают тестовые данные через API хелперы (`helpers/api.ts`):
- **Теплицы (Greenhouses)**: `createTestGreenhouse()` - создает тестовую теплицу с уникальным UID
- **Рецепты с фазами (Recipes)**: `createTestRecipe()` - создает рецепт с опциональными фазами
- **Зоны (Zones)**: `createTestZone()` - создает зону в указанной теплице
- **Биндинги (Bindings)**: `createBinding()` - создает привязку роли к каналу через `/api/channel-bindings`

Все тестовые данные автоматически удаляются после завершения теста через фикстуры (`fixtures/test-data.ts`).

### Использование API хелперов в тестах

```typescript
import { test, expect } from '../fixtures/test-data';

test('example', async ({ apiHelper, testZone }) => {
  // apiHelper уже настроен с авторизацией из storageState
  // testZone автоматически создается и удаляется
  
  // Можно создавать дополнительные данные
  const greenhouse = await apiHelper.createTestGreenhouse();
  const zone = await apiHelper.createTestZone(greenhouse.id);
  
  // Очистка (опционально, если не используете фикстуры)
  await apiHelper.cleanupTestData({
    zones: [zone.id],
    greenhouses: [greenhouse.id],
  });
});
```

## data-testid атрибуты

Все ключевые элементы UI имеют `data-testid` атрибуты для стабильной идентификации в тестах:

- **Login**: `login-form`, `login-email`, `login-password`, `login-submit`, `login-error`
- **Dashboard**: `dashboard-zones-count`, `dashboard-zone-card-{id}`, `dashboard-alerts-count`, `dashboard-events-panel`, `dashboard-event-filter-{kind}`
- **Zone**: `zone-status-badge`, `zone-pause-btn`, `zone-resume-btn`, `zone-command-form`, `zone-events-list`
- **Alerts**: `alerts-filter-active`, `alerts-table`, `alert-row-{id}`, `alert-resolve-btn-{id}`
- **Toast**: `toast-{variant}`, `toast-message`
- **WebSocket**: `ws-status-indicator`, `ws-status-connected`, `ws-status-disconnected`

Полный список констант находится в `constants.ts`.

## Отчеты

После выполнения тестов отчеты сохраняются в:
- HTML отчет: `tests/e2e/reports/playwright/index.html`
- JUnit XML: `tests/e2e/reports/playwright/junit.xml`
- Видео и скриншоты: `test-results/` (для упавших тестов)

## Переменные окружения

- `LARAVEL_URL` - URL Laravel приложения (по умолчанию `http://localhost:8081`)
- `E2E_AUTH_EMAIL` - Email для авторизации (по умолчанию `admin@hydro.local`)
- `E2E_AUTH_PASSWORD` - Пароль для авторизации (по умолчанию `password`)
- `CI` - Если установлена, тесты запускаются в headless режиме с retries=2

## Troubleshooting

### Тесты не находят элементы

1. Убедитесь, что все `data-testid` атрибуты добавлены в компоненты
2. Проверьте, что приложение запущено и доступно по указанному URL
3. Проверьте консоль браузера на наличие ошибок JavaScript

### Ошибки авторизации

1. Убедитесь, что пользователь существует в БД
2. Проверьте переменные окружения `E2E_AUTH_EMAIL` и `E2E_AUTH_PASSWORD`
3. Убедитесь, что сессия не истекла (перезапустите setup тест)

### WebSocket не подключается

1. Проверьте, что Reverb запущен и доступен
2. Проверьте URL WebSocket в конфигурации
3. Убедитесь, что нет проблем с CORS

## Интеграция с CI

Для запуска в CI добавьте в workflow:

```yaml
- name: Run browser tests
  run: |
    cd backend/laravel
    npm run e2e:browser
  env:
    CI: true
    LARAVEL_URL: http://localhost:8081
```
