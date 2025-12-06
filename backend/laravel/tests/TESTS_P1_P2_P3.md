# Тесты для задач P1, P2, P3

## Обзор

Создан полный набор тестов для всех задач рефакторинга P1 (критические), P2 (важные) и P3 (улучшения).

---

## P1: Критические задачи

### P1-1: Типы для core моделей
**Файл:** `resources/js/types/__tests__/types.spec.ts`

**Покрытие:**
- ✅ Проверка структуры типов Zone, Device, Alert, Recipe, Command, Telemetry, Event, Cycle
- ✅ Проверка обязательных полей
- ✅ Проверка опциональных полей

**Тесты:**
- Zone type validation
- Device type validation
- Alert type validation
- Recipe type validation
- Command type validation
- Telemetry types validation
- Event type validation
- Cycle type validation

### P1-2: Автоматическая переподписка на WebSocket
**Файл:** `resources/js/composables/__tests__/useWebSocket.resubscribe.spec.ts`

**Покрытие:**
- ✅ Функция `resubscribeAllChannels`
- ✅ Переподписка на zone commands channels
- ✅ Переподписка на global events channel
- ✅ Обработка ошибок при переподписке
- ✅ Восстановление всех активных подписок после reconnect

**Тесты:**
- Resubscribe to zone commands channels
- Resubscribe to global events channel
- Handle missing Echo gracefully
- Resubscribe to multiple zone commands
- Handle errors during resubscription
- Restore all active subscriptions after reconnect

### P1-3: ErrorBoundary компонент
**Файл:** `resources/js/Components/__tests__/ErrorBoundary.spec.ts`

**Покрытие:**
- ✅ Отображение контента без ошибок
- ✅ Перехват и отображение ошибок
- ✅ Отображение stack trace в development режиме
- ✅ Кнопка "Попробовать снова"
- ✅ Кнопка "На главную"
- ✅ Обработка множественных ошибок

**Тесты:**
- Renders slot content when no error occurs
- Catches and displays error when child component throws
- Displays error message in fallback UI
- Shows stack trace in development mode
- Has "Try Again" button that resets error state
- Has "Go Home" button
- Handles multiple errors correctly

---

## P2: Важные задачи

### P2-1: Виртуализация списков
**Файлы:**
- `resources/js/Pages/Zones/__tests__/Index.virtualization.spec.ts`
- `resources/js/Pages/Devices/__tests__/Index.virtualization.spec.ts`

**Покрытие:**
- ✅ Использование DynamicScroller для Zones
- ✅ Использование RecycleScroller для Devices
- ✅ Передача правильных props (items, item-size, key-field)
- ✅ Фильтрация с виртуализацией
- ✅ Оптимизация с мемоизированным query

**Тесты:**
- Use DynamicScroller for zone list
- Pass filtered zones to DynamicScroller
- Use DynamicScrollerItem for each zone
- Set min-item-size and key-field props
- Filter zones correctly with virtualization
- Optimize filtering with memoized query
- Return all zones when no filters are applied

### P2-2: Кеширование телеметрии в sessionStorage
**Файл:** `resources/js/composables/__tests__/useTelemetry.cache.spec.ts`

**Покрытие:**
- ✅ Сохранение данных в sessionStorage
- ✅ Загрузка данных из sessionStorage при инициализации
- ✅ Очистка истекших записей
- ✅ Обработка переполнения sessionStorage
- ✅ Очистка кеша
- ✅ Обработка поврежденных данных
- ✅ Сохранение history данных

**Тесты:**
- Save telemetry data to sessionStorage
- Load telemetry data from sessionStorage on initialization
- Clear expired entries from sessionStorage
- Handle sessionStorage overflow by removing old entries
- Clear cache from sessionStorage when clearCache is called
- Handle corrupted sessionStorage data gracefully
- Save history data to sessionStorage

### P2-3: ECharts DataZoom для больших графиков
**Файл:** `resources/js/Pages/Zones/__tests__/ZoneTelemetryChart.datazoom.spec.ts`

**Покрытие:**
- ✅ Включение DataZoom для больших наборов данных (>100 точек)
- ✅ Отключение DataZoom для малых наборов (<=100 точек)
- ✅ Наличие обоих типов DataZoom (inside и slider)
- ✅ Корректировка padding для slider
- ✅ Установка флагов large и largeThreshold

**Тесты:**
- Enable DataZoom for large datasets (>100 points)
- Not enable DataZoom for small datasets (<=100 points)
- Include both inside and slider DataZoom types
- Adjust grid bottom padding for DataZoom slider
- Set large and largeThreshold for large datasets
- Not set large flag for small datasets

### P2-4: MQTT статус через dedicated канал
**Файл:** `resources/js/composables/__tests__/useSystemStatus.mqtt.spec.ts`

**Покрытие:**
- ✅ Подписка на канал mqtt.status
- ✅ Обновление статуса при получении MqttStatusUpdated
- ✅ Обработка событий MqttError
- ✅ Переподписка при reconnect WebSocket
- ✅ Fallback логика при недоступности канала
- ✅ Отписка при cleanup

**Тесты:**
- Subscribe to mqtt.status channel on initialization
- Update MQTT status to online when receiving MqttStatusUpdated event
- Update MQTT status to offline when receiving offline event
- Update MQTT status to degraded when receiving degraded event
- Handle MqttError events
- Resubscribe to MQTT channel on WebSocket reconnect
- Use fallback logic when MQTT channel is unavailable
- Unsubscribe from MQTT channel on cleanup

---

## P3: Улучшения

### P3-1: CommandPalette и keyboard shortcuts
**Файлы:**
- `resources/js/Components/__tests__/CommandPalette.spec.ts`
- `resources/js/composables/__tests__/useKeyboardShortcuts.spec.ts`

**Покрытие:**
- ✅ Открытие/закрытие палитры (Ctrl+K, Escape)
- ✅ Отображение статических команд навигации
- ✅ Fuzzy search
- ✅ Навигация по результатам (стрелки, Enter)
- ✅ Подтверждение действий
- ✅ Регистрация/отмена keyboard shortcuts
- ✅ Обработка shortcuts в input элементах

**Тесты:**
- Opens on Ctrl+K keyboard shortcut
- Closes on Escape key
- Displays static navigation commands
- Performs fuzzy search on input
- Navigates to zone when zone command is selected
- Shows confirmation modal for actions requiring confirmation
- Handles keyboard navigation with arrow keys
- Executes command on Enter key
- Highlights search matches in results
- Registers keyboard shortcut
- Handles Ctrl+Z, Ctrl+D, Shift+D shortcuts
- Ignores shortcuts when focus is in input (except Ctrl+K)
- Unregisters keyboard shortcut

### P3-2: Формы валидации
**Файл:** `resources/js/Components/__tests__/ZoneActionModal.validation.spec.ts`

**Покрытие:**
- ✅ Валидация duration_sec для FORCE_IRRIGATION
- ✅ Валидация target_ph для FORCE_PH_CONTROL
- ✅ Валидация target_ec для FORCE_EC_CONTROL
- ✅ Валидация target_temp и target_humidity для FORCE_CLIMATE
- ✅ Валидация intensity и duration_hours для FORCE_LIGHTING
- ✅ Прохождение валидации с валидными значениями
- ✅ Сброс формы при открытии модального окна

**Тесты:**
- Validate duration_sec for FORCE_IRRIGATION
- Validate target_ph for FORCE_PH_CONTROL
- Validate target_ec for FORCE_EC_CONTROL
- Validate target_temp and target_humidity for FORCE_CLIMATE
- Validate intensity and duration_hours for FORCE_LIGHTING
- Pass validation with valid values
- Reset form when modal opens

### P3-3: Обработка ошибок в формах
**Файл:** `resources/js/composables/__tests__/useFormValidation.spec.ts`

**Покрытие:**
- ✅ Определение наличия ошибок
- ✅ Получение первой ошибки
- ✅ Проверка ошибки для конкретного поля
- ✅ Получение классов для полей с ошибками
- ✅ Очистка ошибок
- ✅ Валидация числовых диапазонов
- ✅ Валидация минимальной длины
- ✅ Валидация email

**Тесты:**
- Detect errors in form
- Return first error
- Check if specific field has error
- Return error classes for field with error
- Return normal classes for field without error
- Clear error for specific field
- Clear all errors
- Validate number range correctly
- Validate minimum length
- Validate email format

### P3-4: Оптимизация производительности
**Файл:** `resources/js/composables/__tests__/usePerformance.spec.ts`

**Покрытие:**
- ✅ Мемоизированная фильтрация
- ✅ Мемоизированный lowercase query
- ✅ Мультифильтрация с несколькими условиями
- ✅ Обновление при изменении данных
- ✅ Возврат всех элементов при отсутствии фильтров

**Тесты:**
- Filter items correctly
- Update when items change
- Work with computed items
- Convert query to lowercase
- Update when query changes
- Handle empty string
- Filter with multiple conditions
- Return all items when no filters are active
- Update when filters change

---

## Статистика тестов

### Всего создано тестовых файлов: 11

1. `ErrorBoundary.spec.ts` - 7 тестов
2. `useWebSocket.resubscribe.spec.ts` - 6 тестов
3. `useTelemetry.cache.spec.ts` - 7 тестов
4. `useSystemStatus.mqtt.spec.ts` - 8 тестов
5. `CommandPalette.spec.ts` - 9 тестов
6. `useKeyboardShortcuts.spec.ts` - 7 тестов
7. `useFormValidation.spec.ts` - 10 тестов
8. `usePerformance.spec.ts` - 9 тестов
9. `ZoneTelemetryChart.datazoom.spec.ts` - 6 тестов
10. `Index.virtualization.spec.ts` (Zones) - 8 тестов
11. `Index.virtualization.spec.ts` (Devices) - 6 тестов
12. `types.spec.ts` - 8 тестов
13. `ZoneActionModal.validation.spec.ts` - 7 тестов

### Всего тестов: ~98 тестов

---

## Запуск тестов

```bash
# Запуск всех тестов
npm test

# Запуск с UI
npm run test:ui

# Запуск конкретного файла
npm test -- ErrorBoundary.spec.ts

# Запуск в watch режиме
npm test -- --watch
```

---

## Покрытие

Тесты покрывают:
- ✅ Все компоненты из P1, P2, P3
- ✅ Все composables из P1, P2, P3
- ✅ Все типы из P1-1
- ✅ Критические функции (resubscribe, cache, validation)
- ✅ Оптимизации производительности

---

## Примечания

- Все тесты используют Vitest
- Моки для внешних зависимостей (Echo, router, API)
- Тесты изолированы и не зависят друг от друга
- Используются стандартные практики Vue 3 Testing

