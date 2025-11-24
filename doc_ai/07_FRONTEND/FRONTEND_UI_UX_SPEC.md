# FRONTEND_UI_UX_SPEC.md
# Полная спецификация UI/UX фронтенда 2.0 (Laravel + Inertia + Vue 3)
# Инструкция для ИИ-агентов

Этот документ определяет **правила, архитектуру и UX-паттерны** фронтенда 
гидропонной системы 2.0, работающего на:

- Laravel (Inertia backend)
- Vue 3 (Composition API)
- Tailwind CSS
- PostgreSQL (данные через Inertia)
- WebSockets (опционально)

Документ обязателен для ИИ-агентов при создании/изменении фронтенда.

---

# 1. Основные цели UI

UI должен быть:

- **информационно насыщенным**, но не перегруженным;
- **реалтайм**, если доступен websockets;
- **модульным**, легко расширяемым;
- **совместимым с мобильными устройствами**;
- минималистичным, вдохновлённым стилями:
 - Vercel/Dashboard,
 - shadcn/ui,
 - Linear.app,
 - Home Assistant.

---

# 2. Структура страниц (Inertia Pages)

```
resources/js/Pages/
 Dashboard/Index.vue (ролевые дашборды)
 Dashboard/Dashboards/
   - AgronomistDashboard.vue
   - AdminDashboard.vue
   - EngineerDashboard.vue
   - OperatorDashboard.vue
   - ViewerDashboard.vue
 Zones/Index.vue
 Zones/Show.vue
 Zones/ZoneCard.vue
 Zones/ZoneTelemetryChart.vue
 Devices/Index.vue
 Devices/Show.vue
 Devices/Add.vue
 Devices/DeviceChannelsTable.vue
 Recipes/Index.vue
 Recipes/Show.vue
 Recipes/Edit.vue
 Alerts/Index.vue
 Settings/Index.vue
 Admin/Index.vue
 Admin/Zones.vue
 Admin/Recipes.vue
 Greenhouses/Create.vue
 Profile/Edit.vue
 Setup/Wizard.vue
 Auth/ (Login, Register, etc.)
```

### Правило для ИИ:
- каждая новая страница должна быть создана в Pages и входить через Inertia.

---

# 3. Навигация и лейауты

## 3.1. Главный Layout: AppLayout.vue

Содержит:

- левое меню:
 - Dashboard
 - Zones
 - Devices
 - Recipes
 - Alerts
 - Settings
- основной контейнер
- заголовок (page title)
- слот для действий справа (`actions`)

### UX требования:
- стабильное меню слева, скрытие на мобильных;
- тёмная тема по умолчанию, переключатель в Settings.

---

# 4. Dashboard (Главная)

`Pages/Dashboard/Index.vue`

### Отображает:

- Карточки теплиц (Greenhouses)
- Количество зон
- Количество активных alert’ов
- Последние события ZoneEvents
- Самые проблемные зоны (по статусу/алертам)

### Компоненты:

- `StatCard.vue`
- `ZoneCard.vue`
- `Alerts/AlertCard.vue`
- `Events/EventRow.vue`

### Правила UX:
- показывать только самую важную информацию,
- удобная навигация «в одну плитку».

---

# 5. Zones (Список зон)

`Pages/Zones/Index.vue`

Содержит:

- плитки всех зон
- фильтрация по статусу (RUNNING / PAUSED / ALARM / WARNING)
- сортировка (по имени, по алертам)

### Каждая зона — `ZoneCard.vue`:

- имя зоны
- статус в виде `Badge.vue`
- быстрые метрики:
 - pH
 - EC
 - Temp
 - Humidity
- кнопка перехода «Подробнее»

---

# 6. Zone Details (Главная страница зоны)

`Pages/Zones/Show.vue`

Это **центральный экран фронтенда**.

Секции:

## 6.1. Заголовок
- имя зоны
- статус
- активная фаза (seedling / veg / bloom)
- кнопки:
 - Pause/Resume Zone
 - Next Phase
 - Irrigate Now
 - Recalibrate pH/EC (если устройство поддерживает)

## 6.2. Стат-карточки

`ZoneTargets.vue` + `StatCard.vue`:

- pH (current vs target)
- EC
- Температура воздуха
- Влажность воздуха
- Температура воды
- Уровень воды
- Световой режим

## 6.3. Графики

`ZoneTelemetryChart.vue` показывает:

- pH vs время
- EC vs время
- Temp vs время
- Humidity vs время

Особенности:
- auto-refresh
- кнопки: 1H / 24H / 7D / 30D / ALL
- smooth линия (ApexCharts или ECharts)

## 6.4. Devices

Список устройств, привязанных к зоне.

Компоненты:
- `DeviceCard.vue`
- `DeviceChannelsTable.vue`

Каждый узел показывает:
- статус
- каналы
- действие (test channel → send command)

## 6.5. Events (История событий)

`ZoneEventsList.vue`

- сортировка по времени
- цветовая кодировка типов событий
- пагинация

---

# 7. Pages for Devices

`Pages/Devices/Index.vue`
`Pages/Devices/Show.vue`

Отображают:

- список всех узлов
- фильтрация по типу: PH / EC / Climate / Irrigation
- статус (ONLINE/OFFLINE)
- RSSI
- прошивка узла (fw version)
- действия диагностики (restart, test channels)

UX:
- минимализм
- всё, что касается железа, — только здесь

---

# 8. Recipes (Рецепты)

## 8.1. Index

`Pages/Recipes/Index.vue`

Показывает:

- список рецептов
- кнопка “Создать рецепт”

## 8.2. Show

`Pages/Recipes/Show.vue`

Включает:

- список фаз
- цели (targets)
- длительность
- кривые роста

## 8.3. Edit

Форма редактирования рецепта:

- таблица фаз
- цели pH / EC / temp / humidity / light
- drag-and-drop изменения фаз
- валидация

---

# 9. Alerts (Алерты)

`Pages/Alerts/Index.vue`

Каждый alert показывает:

- тип (PH_HIGH, TEMP_LOW и т.д.)
- зона
- время
- статус ACTIVE/RESOLVED
- кнопку “Подтвердить”

UX:
- показывать цветовые индикаторы,
- сгруппировать по зонам,
- фильтр только активные.

---

# 10. Settings

Содержит:

- переключатель темы (light/dark)
- настройки ESP автообновления (если появится)
- управление пользователями (если нужно)
- системные параметры

---

# 11. Компоненты (стандарты)

## 11.1. Badge.vue

Варианты:

- success
- warning
- danger
- info
- neutral

## 11.2. Modal.vue

Поддерживает:
- title
- description
- slot для форм
- footer с кнопками

## 11.3. DataTable.vue

Функции:
- серверная пагинация
- сортировка
- фильтрация
- sticky header
- адаптивный дизайн

---

# 12. Стиль UI (Tailwind)

### Основная палитра:
- тёмно-синий фон (для dark)
- светлый серый фон (для light)
- акцентный синий/бирюзовый
- мягкие радиусы и тени (shadow-sm, rounded-xl)

### Правила:
- избегать крупных теней
- избегать цветастых кнопок
- использовать цветовые акценты **только** в статуc-бейджах

---

# 13. Реалтайм данные (WebSockets)

Laravel → WebSockets может отправлять:

- обновления last telemetry,
- появление alert,
- смену статуса зоны,
- завершение команды (ACK).

ИИ должен:
- использовать Laravel Echo,
- обновлять только локальное состояние (не перезапрашивать Inertia страницу).

---

# 14. Правила для ИИ-агентов

### ИИ может:

- добавлять новые UI-секции,
- улучшать табличные компоненты,
- добавлять новые графики,
- создавать новые страницы в Pages.

### ИИ не может:

- менять существующую структуру Pages,
- переименовывать каналы/статусы/зоны,
- ломать AppLayout,
- менять структуру Inertia props без обновления backend-контроллеров.

---

# 15. Чек-лист для ИИ

1. Страница создаётся в Pages?
2. Компоненты лежат в Components?
3. Используется `<script setup>`?
4. Нет лишней логики во Vue?
5. Tailwind-классы читаемые?
6. Не изменён формат доменных данных?
7. Взаимодействие выполняется только через Inertia router?

---

# Конец файла FRONTEND_UI_UX_SPEC.md
