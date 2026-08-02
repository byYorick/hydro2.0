# AUTH_SYSTEM.md
# Полная система авторизации и аутентификации 2.0
# Laravel Sanctum • Roles • Permissions • Tokens • API Security • UI Restrictions

**Дата обновления:** 2026-08-02 (API login без LoginRequest lockout; middleware `role`/`admin`; PAT abilities `*`; dual throttle note).

Документ описывает всю модель авторизации (Auth System) в системе 2.0:
от входа пользователя до распределения прав, токенов и API-доступа.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Общая архитектура безопасности

Auth в 2.0 состоит из:

1. **Laravel Sanctum** — хранение токенов и сессий 
2. **Ролевая модель (RBAC)** 
3. **Permissions (разрешения для API и UI)** 
4. **API Tokens для автоматизации и Python** 
5. **Лимиты доступа и контроль действий** 
6. **Аудит действий (Events)** 

---

# 2. Пользователи и роли

Все пользователи хранятся в таблице:

## 2.1. Таблица users

```
id PK
name
email UNIQUE
password (bcrypt)
role VARCHAR (admin/operator/viewer/agronomist/engineer)
created_at
updated_at
```

---

# 3. Ролевые уровни

## 3.1. role = admin
Полный доступ:

- управление пользователями
- управление зонами
- рецепты и фазы
- узлы, устройства
- OTA
- события и тревоги
- настройки системы

## 3.2. role = operator
Ограниченный доступ:

- управление зонами 
- ручной полив 
- ручное дозирование 
- правка рецептов 
- разрешение тревог 
- просмотр логов 

НЕ может:

- менять пользователей 
- менять системные настройки 
- выполнять OTA на все узлы (только разрешённые)

## 3.3. role = viewer
Только просмотр:

- зоны 
- рецепты 
- контроллеры 
- история telemetries 
- тревоги и события 

НЕ может:

- создавать команды 
- менять настройки 

## 3.4. role = agronomist
Профиль технолога выращивания:

- управление циклами выращивания (grow-cycle)
- управление ревизиями рецептов и публикацией DRAFT
- доступ к операционным данным и аналитике

## 3.5. role = engineer
Профиль инженерной эксплуатации:

- операции диагностики и сервисные действия
- работа с логами и инфраструктурным наблюдением
- без прав управления пользователями

---

# 4. API Tokens (Sanctum)

## 4.1. Генерация токена

```
POST /api/auth/login
{
 "email": "user@mail.com",
 "password": "******"
}
```

Ответ:
```
{
  "status": "ok",
  "data": {
    "token": "xxxxxxxx"
  }
}
```

## 4.2. Роль не в token abilities

`AuthController::login` создаёт PAT через `createToken('api')` **без** scoped abilities → Sanctum default `['*']`.  
Авторизация — по `users.role` + middleware `role`/`admin` + Policy classes.  
Scoped Sanctum abilities (`zones:read`, …) — **planned**, не production contract.

## 4.3. Ответ login/me

Роль отдаётся в JSON пользователя (`role`), не как `token->abilities`.

---

# 5. Role capabilities (logical)

Логическая матрица возможностей по роли (UI + Policies). **Не** Sanctum token abilities — enforcement через `EnsureUserHasRole` / `EnsureAdmin` и `*Policy`.

ТОП‑уровень:

| Permission | admin | operator | agronomist | engineer | viewer |
|------------|--------|----------|------------|----------|--------|
| zones.read | yes | yes | yes | yes | yes |
| zones.write | yes | yes | limited | limited | no |
| nodes.write | yes | yes | limited | yes | no |
| telemetry.read | yes | yes | yes | yes | yes |
| commands.write | yes | yes | yes | yes | no |
| recipes.write | yes | limited | yes | limited | no |
| grow_cycles.manage | yes | limited | yes | no | no |
| users.manage | yes | no | no | no | no |

---

# 6. Middleware (Laravel)

Aliases в `bootstrap/app.php`:

## 6.1. `admin` → `EnsureAdmin`

Изоляция системных/admin эндпоинтов: `middleware('admin')`.

## 6.2. `role` → `EnsureUserHasRole`

Проверка роли: `middleware('role:admin,operator')` и т.п.

## 6.3. Token ability middleware

`CheckTokenAbility` / `$token->can('…')` — **не зарегистрированы** (planned). Сейчас ability-checks не используются.

---

# 7. Web UI ограничения

UI скрывает:

| Роль | Скрытые разделы |
|------|------------------|
| viewer | всё управление |
| operator | управление пользователями |
| agronomist | инженерные логи и часть сервисных разделов |
| engineer | разделы управления рецептами и grow-cycle |

Vue должен фильтровать доступ по `props.auth.user.role`.

---

# 8. Ограничения API по ролям

### 8.1. Пример: отправка команды
```
POST /api/zones/{zone}/commands
```

| Роль | Доступ |
|-------|--------|
| admin | ✔ |
| operator | ✔ |
| agronomist | ✔ |
| engineer | ✔ |
| viewer | ✖ |

### 8.2. OTA — **planned / not implemented**

Целевой endpoint (ещё нет в `routes/api.php`):

```
POST /api/ota/push
```

| Роль | Доступ (target) |
|--------|--------|
| admin | ✔ |
| operator | частично |
| agronomist | ✖ |
| engineer | частично |
| viewer | ✖ |

---

# 9. Аудит действий (Events)

Каждое критичное действие создаёт событие:

- вход пользователя
- создание команды
- изменение рецепта
- закрытие тревоги
- запуск OTA
- смена настроек зоны

Пример:
```
USER_ACTION
{
 "user_id": 1,
 "action": "command_create",
 "command_id": 54
}
```

---

# 10. Безопасность паролей

- bcrypt
- минимальная длина **8** (`Password::defaults()`; кастомный override в AppServiceProvider отсутствует)
- проверка через Laravel Validation (`PasswordController`, registration/reset)
- дополнительные правила сложности — только если явно настроены через `Password::defaults()`

---

# 11. Двухфакторная аутентификация (2FA) — 2.0

План на будущее:

- TOTP (Google Authenticator)
- резервные коды
- привязка устройства

---

# 12. Session Security

- истечение сессии: **120 минут** idle (`config/session.php` → `env('SESSION_LIFETIME', 120)`)
- истечение API-токена Sanctum: **`null`** (no auto-expire), пока не задано иное в published `config/sanctum.php` / env
- logout всех токенов при смене пароля: **не реализовано** (`PasswordController` только обновляет hash; revoke tokens — planned)

---

# 13. Лимитирование запросов (Rate Limiting)

SoT throttle defaults:

- **API middleware default:** `bootstrap/app.php` (`env('API_THROTTLE', …)`) + `config/services.php` (`services.api.throttle_default` / `throttle_internal`)
- **Route-level overrides:** `backend/laravel/routes/api.php` (auth, system, node_register и т.д.)

Значения:

- **Auth API** (`POST /api/auth/login`, `/logout`, `/me`): **10 запросов/мин по IP** (`throttle:10,1`).  
  Lockout **5 неудач per email|IP** (`LoginRequest`) — **только web Breeze** (`AuthenticatedSessionController`).  
  API `AuthController::login` использует inline `validate` + `Auth::attempt` **без** этого lockout.
- **Стандартные authenticated API**: конфиг **120/min** (`API_THROTTLE`), но группа часто имеет **двойной** throttle (prepend в `bootstrap/app.php` + route `throttle:` в `routes/api.php`) → effective ≈ **~60 req/min/IP** на один hit, пока дубль не снят.
- **System endpoints** (`GET /api/system/health`, `/api/system/scheduler/metrics`): **300 запросов/мин** — выше для polling мониторинга.
- **Регистрация узлов** (`/api/nodes/register`): `throttle:node_register` + `ip.whitelist` (см. `services.node_registration.allowed_ips`).

---

# 14. Запрет доступа снаружи (Network Rules)

- UI HTTPS-only: **planned/prod**; local docker dev — **HTTP** `http://localhost:8080`
- API доступен только из LAN (prod network posture)
- MQTT закрыт для WAN
- Python и ESP32 общаются через внутреннюю сеть Docker/LAN

---

# 15. Правила для ИИ

ИИ может:

- добавлять новые роли 
- расширять abilities 
- усиливать валидацию 
- добавлять 2FA 

ИИ НЕ может:

- удалять роли 
- ослаблять права 
- отключать токены 
- снижать требования безопасности 

---

# 16. Чек‑лист безопасности Auth System

1. Используется Sanctum? 
2. Все токены привязаны к ролям? 
3. Permissions настроены? 
4. UI скрывает запрещённые разделы? 
5. Логи записывают действия? 
6. HTTPS включён? 
7. API недоступен снаружи? 
8. Пароли надёжные? 
9. Роли корректно применяются? 

---

# Конец файла AUTH_SYSTEM.md
