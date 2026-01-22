# TECH_STACK_LARAVEL_INERTIA_VUE3_PG.md
# Инструкция для ИИ-агентов по работе с проектом Laravel + Inertia + Vue 3 + PostgreSQL

Документ описывает, **как ИИ-агенты и разработчики должны работать** с backend-частью проекта
на стеке Laravel + PostgreSQL + Inertia + Vue 3, чтобы не ломать архитектуру и стиль.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общая идея архитектуры

1. **Backend:** Laravel 10/11 (PHP 8.2+) + PostgreSQL.
2. **Frontend:** Inertia SPA + Vue 3 (Composition API).
3. **Маршрутизация:** `routes/web.php` (Inertia + защищённые страницы) и `routes/api.php` (REST).
4. **Доступ к данным:** Eloquent-модели, запросы через репозитории/сервисы.
5. **Реалтайм:** Laravel Broadcasting/WebSockets (по мере внедрения).

Backend остаётся «толстым» (доменная логика внутри Laravel/Services), 
Frontend — «тонкий» (отображение, валидация на UI, UX).

---

## 2. Структура Laravel-проекта

```text
backend-laravel/
 app/
 Http/
 Controllers/
 Middleware/
 Requests/
 Models/
 Services/
 Policies/
 Events/
 Listeners/
 Jobs/
 database/
 migrations/
 seeders/
 routes/
 web.php
 api.php
 resources/
 js/
 Pages/
 Components/
 composables/
 config/
 tests/
```

### 2.1. Controllers

- В файле `app/Http/Controllers`.
- Логика минимальна: валидация через Form Request → вызов Service → возврат ответа/Inertia.

### 2.2. Services

- В `app/Services`.
- Реализуют сценарии бизнес-логики (use cases).
- Примеры: `ZoneService`, `RecipeService`, `NodeService`, `AlertService`.

### 2.3. Models

- В `app/Models`.
- Описывают связи (hasMany, belongsToMany и т.п.).
- Не должны содержать сложную бизнес-логику.

### 2.4. Миграции

- В `database/migrations`.
- Любые изменения схемы БД **обязаны** проходить через миграции.

---

## 3. Структура фронтенда (Vue 3 + Inertia)

```text
resources/js/
 Pages/
 Dashboard/
 Zones/
 Nodes/
 Recipes/
 Alerts/
 Settings/
 Components/
 charts/
 forms/
 layout/
 composables/
 useApi.ts
 useZoneStore.ts
```

- Каждая страница = Inertia Page (например, `Zones/Index.vue`, `Zones/Show.vue`).
- Компоненты должны быть переиспользуемыми (графики, таблицы).

---

## 4. Правила для ИИ-агентов по коду

1. **Не создавать новые каталоги верхнего уровня без необходимости.**
2. **Не раздувать контроллеры.**
 - Если логика > ~30–50 строк → выносить в Service.
3. **Все новые таблицы и поля должны быть описаны в `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.**
4. **Не менять существующие миграции.**
 - Для изменений схемы всегда создаётся новая миграция.
5. **Соблюдать PSR-12 / Laravel-стиль.**
6. **При добавлении API обязательно обновлять `REST_API_REFERENCE.md` и `API_SPEC_FRONTEND_BACKEND_FULL.md`.**

---

## 5. Интеграция с Python-сервисом и AI

- Все точки интеграции должны быть сосредоточены в ограниченном наборе Service-классов
 (например, `PythonBridgeService`, `AiGatewayService`). 
- Нельзя рассыпать вызовы внешних API по контроллерам.

Пример:

```php
class ZoneCommandController extends Controller
{
 public function store(SendZoneCommandRequest $request, Zone $zone, PythonBridgeService $bridge)
 {
 $commandId = $bridge->sendZoneCommand($zone, $request->validated());
 return response()->json(['status' => 'ok', 'command_id' => $commandId]);
 }
}
```

---

## 6. Работа с PostgreSQL

- Использовать стандартные типы (integer, boolean, timestamp, jsonb).
- Индексы добавлять осмысленно (на часто используемые фильтры).
- Не использовать raw-SQL без необходимости, предпочитать Query Builder/Eloquent.

---

## 7. Тестирование

- При добавлении новой функциональности создавать feature-тесты, где это оправдано.
- ИИ-агентам:
 - не удалять существующие тесты;
 - не вырубать проверки/валидацию «для удобства».

---

## 8. Вывод

Этот документ определяет **рамки работы** ИИ-агентов и разработчиков в Laravel-части проекта.

Соблюдая его, можно безопасно:

- расширять доменную модель,
- добавлять реальные фичи UI,
- интегрироваться с Python-сервисом и AI,
- не ломая архитектуру и не превращая проект в «спагетти».
