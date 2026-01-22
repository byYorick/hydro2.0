# FRONTEND_TESTING.md
# Стратегия тестирования Frontend 2.0

Этот документ описывает подход к тестированию фронтенда системы управления теплицей 2.0, включая unit-тесты компонентов, интеграционные тесты страниц и E2E-тесты.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общая стратегия

### 1.1. Три уровня тестирования

1. **Unit/Component тесты (Vitest + Vue Test Utils)**
   - Тестирование отдельных компонентов Vue
   - Проверка логики вычисляемых свойств, методов, событий
   - Моки зависимостей (axios, Inertia, Pinia stores)

2. **Интеграционные тесты (Vitest + Vue Test Utils)**
   - Тестирование взаимодействия компонентов на странице
   - Проверка загрузки данных через API
   - Проверка обработки ошибок

3. **E2E тесты (Playwright)**
   - Полное тестирование пользовательских сценариев
   - Проверка навигации, взаимодействия с UI
   - Проверка реальных HTTP-запросов и WebSocket-соединений

---

## 2. Unit/Component тесты

### 2.1. Тестируемые компоненты

#### ZoneTargets.vue
**Расположение:** `resources/js/Components/__tests__/ZoneTargets.spec.ts`

**Проверяемые сценарии:**
- Отображение карточек только для метрик с целями
- Индикаторы статуса (OK/Высокий/Низкий) в зависимости от значений
- Правильный расчет вариантов (success/warning/danger)
- Отображение целей как диапазон min–max или target
- Форматирование температуры и влажности
- Обработка граничных случаев (отрицательные значения, NaN, undefined)

**Граничные случаи:** `ZoneTargets.edge.spec.ts`
- Отсутствие целей
- Значения на границе диапазона
- Отрицательные и очень большие значения
- NaN значения
- Узкие диапазоны

#### ZoneTelemetryChart.vue
**Расположение:** `resources/js/Pages/Zones/__tests__/ZoneTelemetryChart.spec.ts`

**Проверяемые сценарии:**
- Отображение заголовка и кнопок времени (1H, 24H, 7D, 30D, ALL)
- Выделение активной кнопки времени
- Эмиссия события `time-range-change` при клике
- Передача данных в ChartBase компонент
- Обработка пустых данных

#### Badge.vue
**Расположение:** `resources/js/Components/__tests__/Badge.spec.ts`

**Проверяемые сценарии:**
- Отображение slot content
- Применение variant классов (success, warning, danger, info, neutral)

---

## 3. Интеграционные тесты страниц

### 3.1. Zones/Show.vue

**Расположение:** 
- `resources/js/Pages/Zones/__tests__/Show.spec.ts`
- `resources/js/Pages/Zones/__tests__/Show.integration.spec.ts`

**Проверяемые сценарии:**

#### Основные функции:
- Отображение информации о зоне
- Отображение компонента ZoneTargets с телеметрией и целями
- Отображение графиков pH и EC с данными
- Отображение устройств зоны
- Отображение событий с цветовой кодировкой
- Отображение блока Cycles
- Кнопки управления для операторов и админов

#### Интеграция с API:
- Загрузка данных истории для графиков при монтировании
- Правильное формирование параметров времени для разных диапазонов
- Обработка изменения диапазона времени через событие
- Отправка команды FORCE_IRRIGATION при клике на Irrigate Now
- Отправка команды FORCE_* при запуске цикла
- Обработка ошибок загрузки графиков gracefully

#### Граничные случаи:
- Правильное вычисление варианта статуса для разных статусов
- Обработка отсутствия данных графиков
- Обработка ошибок загрузки

---

## 4. E2E тесты

### 4.1. Общие тесты (smoke)

**Расположение:** `tests/e2e/smoke.spec.ts`

**Проверяемые сценарии:**
- Загрузка главной страницы (Dashboard)
- Отображение списка зон
- Отображение списка алертов
- Загрузка страницы детали зоны

### 4.2. Zones/Show E2E

**Расположение:** `tests/e2e/zones-show.spec.ts`

**Проверяемые сценарии:**
- Отображение информации о зоне
- Отображение блока Target vs Actual
- Отображение графиков pH и EC
- Отображение устройств зоны
- Отображение блока Cycles
- Отображение событий
- Кнопки управления для оператора
- Изменение диапазона времени графика

---

## 5. Конфигурация тестов

### 5.1. Vitest

**Файл конфигурации:** `vitest.config.ts`

```typescript
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './resources/js'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['resources/js/**/*.spec.ts', 'resources/js/**/*.spec.tsx'],
  },
})
```

**Setup файл:** `vitest.setup.ts`

- Расширение matchers из `@testing-library/jest-dom`

### 5.2. Playwright

**Файл конфигурации:** `playwright.config.ts`

- Настройка webServer для Laravel dev server
- Конфигурация браузеров (Chromium, Firefox, WebKit)
- HTML отчеты

---

## 6. Моки и заглушки

### 6.1. Axios моки

Для тестирования компонентов, использующих axios:

```typescript
const axiosGetMock = vi.fn()
const axiosPostMock = vi.fn()

vi.mock('axios', () => ({
  default: {
    get: (url: string, config?: any) => axiosGetMock(url, config),
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
  },
}))

// В beforeEach:
axiosGetMock.mockImplementation((url: string, config?: any) => {
  return Promise.resolve({
    data: {
      data: [/* тестовые данные */],
    },
  })
})
```

### 6.2. Inertia моки

```typescript
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      // тестовые props
    },
  }),
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))
```

### 6.3. Компоненты-моки

Для упрощения тестов больших компонентов используются моки:

```typescript
vi.mock('@/Components/ZoneTargets.vue', () => ({
  default: { 
    name: 'ZoneTargets', 
    props: ['telemetry', 'targets'],
    template: '<div class="zone-targets">Targets</div>' 
  },
}))
```

---

## 7. Структура тестовых файлов

```
backend/laravel/
├── resources/js/
│   ├── Components/
│   │   ├── __tests__/
│   │   │   ├── Badge.spec.ts
│   │   │   ├── ZoneTargets.spec.ts
│   │   │   └── ZoneTargets.edge.spec.ts
│   │   └── ZoneTargets.vue
│   ├── Pages/
│   │   ├── Zones/
│   │   │   ├── __tests__/
│   │   │   │   ├── Index.spec.ts
│   │   │   │   ├── Show.spec.ts
│   │   │   │   ├── Show.integration.spec.ts
│   │   │   │   └── ZoneTelemetryChart.spec.ts
│   │   │   └── Show.vue
│   │   ├── Alerts/
│   │   │   └── __tests__/
│   │   │       └── Index.spec.ts
│   │   └── Devices/
│   │       └── __tests__/
│   │           └── Index.spec.ts
│   └── stores/
│       └── __tests__/
│           └── zones.spec.ts
├── tests/
│   └── e2e/
│       ├── smoke.spec.ts
│       └── zones-show.spec.ts
├── vitest.config.ts
├── vitest.setup.ts
└── playwright.config.ts
```

---

## 8. Запуск тестов

### 8.1. Unit/Component тесты

```bash
cd backend/laravel
npm test              # запустить все тесты один раз
npm run test:ui       # запустить в UI режиме
```

### 8.2. E2E тесты

```bash
cd backend/laravel
npm run e2e           # запустить все E2E тесты
```

### 8.3. В CI/CD

Тесты автоматически запускаются в GitHub Actions:
- Vitest: JUnit-отчет и coverage (артефакты Actions)
- Playwright: HTML-репорт (артефакт Actions)

---

## 9. Покрытие тестами

### 9.1. Текущее покрытие

**Компоненты:**
- ✅ ZoneTargets.vue (unit + edge cases)
- ✅ ZoneTelemetryChart.vue (unit)
- ✅ Badge.vue (unit)

**Страницы:**
- ✅ Zones/Index.vue (unit)
- ✅ Zones/Show.vue (unit + integration)
- ✅ Alerts/Index.vue (unit)
- ✅ Devices/Index.vue (unit)

**Stores:**
- ✅ zones store (unit)

**E2E:**
- ✅ Dashboard (smoke)
- ✅ Zones/Show (smoke + детальные сценарии)

### 9.2. Планы расширения

- [ ] Добавить тесты для Recipes/Show.vue и Recipes/Edit.vue
- [ ] Добавить тесты для Devices/Show.vue
- [ ] Расширить E2E тесты для критических пользовательских потоков
- [ ] Добавить тесты для WebSocket-обновлений
- [ ] Увеличить покрытие edge cases

---

## 10. Лучшие практики

### 10.1. Написание тестов

1. **Один тест = одна проверка**
   - Каждый тест должен проверять один конкретный аспект поведения

2. **Используйте описательные имена**
   - `it('показывает индикатор "OK" для значения в диапазоне')`

3. **Моки должны быть минимальными**
   - Мокируйте только внешние зависимости
   - Не мокируйте тестируемый код

4. **Тестируйте поведение, а не реализацию**
   - Фокусируйтесь на том, что делает компонент, а не на том, как

### 10.2. Поддержка тестов

1. **Обновляйте тесты при изменении компонентов**
   - Тесты должны отражать текущее поведение

2. **Рефакторинг тестов**
   - Если тесты становятся сложными, стоит пересмотреть структуру

3. **Используйте общие утилиты**
   - Создавайте helper-функции для повторяющихся паттернов

---

## 11. Отладка тестов

### 11.1. Vitest

```bash
# Запустить тесты в watch режиме
npm run test:ui

# Запустить конкретный тест
npx vitest run Zones/Show.spec.ts
```

### 11.2. Playwright

```bash
# Запустить в headed режиме
npx playwright test --headed

# Запустить в debug режиме
npx playwright test --debug
```

---

## 12. Связанные документы

- `../DEV_CONVENTIONS.md` - общие конвенции разработки
- `FRONTEND_ARCH_FULL.md` - архитектура фронтенда
- `FRONTEND_UI_UX_SPEC.md` - спецификация UI/UX
- `../08_SECURITY_AND_OPS/TESTING_AND_CICD_STRATEGY.md` - общая стратегия тестирования

---

## Конец файла FRONTEND_TESTING.md
