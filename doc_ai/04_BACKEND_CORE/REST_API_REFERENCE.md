# REST_API_REFERENCE.md
# Полный референс REST API для системы 2.0

Документ служит **справочником** по основным REST-эндпоинтам Laravel-backend,
которые используются фронтендом, Android и Python-сервисом (частично).

Он дополняет `API_SPEC_FRONTEND_BACKEND_FULL.md`, но сфокусирован именно на списке URL и их назначении.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Auth

| Метод | Путь | Auth | Описание |
|-------|---------------------|------|-----------------------------------|
| POST | /api/auth/login | public | Вход, выдача токена |
| POST | /api/auth/logout | auth:sanctum | Выход, отзыв токена |
| GET | /api/auth/me | auth:sanctum | Инфо о текущем пользователе |

---

## 2. Greenhouses

| Метод | Путь | Auth | Описание |
|-------|-------------------------|------|-------------------------------|
| GET | /api/greenhouses | auth:sanctum | Список теплиц |
| POST | /api/greenhouses | auth:sanctum (admin/operator) | Создать теплицу |
| GET | /api/greenhouses/{id} | auth:sanctum | Детали теплицы |
| PATCH | /api/greenhouses/{id} | auth:sanctum (admin/operator) | Обновить теплицу |
| DELETE| /api/greenhouses/{id} | auth:sanctum (admin) | Удалить (если безопасно) |

---

## 3. Zones

| Метод | Путь | Auth | Описание |
|-------|-----------------------|------|------------------------------------------------|
| GET | /api/zones | auth:sanctum | Список зон (фильтры по теплице, статусу) |
| POST | /api/zones | auth:sanctum (operator/admin) | Создать зону |
| GET | /api/zones/{id} | auth:sanctum | Детали зоны + активный рецепт |
| PATCH | /api/zones/{id} | auth:sanctum (operator/admin) | Обновить параметры зоны |
| DELETE| /api/zones/{id} | auth:sanctum (admin) | Удалить зону (если нет активных зависимостей) |

Доп. действия:

| Метод | Путь | Auth | Описание |
|-------|-----------------------------------|------|------------------------------------|
| POST | /api/zones/{id}/fill | auth:sanctum (operator/admin/agronomist/engineer) | Режим наполнения зоны |
| POST | /api/zones/{id}/drain | auth:sanctum (operator/admin/agronomist/engineer) | Режим слива зоны |
| POST | /api/zones/{id}/calibrate-flow | auth:sanctum (operator/admin/agronomist/engineer) | Калибровка датчика расхода |
| POST | /api/zones/{id}/calibrate-pump | auth:sanctum (operator/admin/agronomist/engineer) | Калибровка дозирующей помпы (ml/sec) |
| POST | /api/zones/{id}/grow-cycles | auth:sanctum (operator/admin/agronomist/engineer) | Создать новый grow cycle для зоны |
| POST | /api/grow-cycles/{id}/pause | auth:sanctum (operator/admin/agronomist/engineer) | Пауза grow cycle |
| POST | /api/grow-cycles/{id}/resume | auth:sanctum (operator/admin/agronomist/engineer) | Возобновление grow cycle |
| POST | /api/grow-cycles/{id}/set-phase | auth:sanctum (operator/admin/agronomist/engineer) | Ручной переход фазы grow cycle |
| POST | /api/grow-cycles/{id}/advance-phase | auth:sanctum (operator/admin/agronomist/engineer) | Переход на следующую фазу grow cycle |
| POST | /api/zones/{id}/commands | auth:sanctum (operator/admin/agronomist/engineer) | Отправить команду зоне |
| GET | /api/zones/{id}/scheduler-tasks | auth:sanctum | Последние scheduler-task по зоне (`lifecycle`, опц. `timeline` через `include_timeline=1`) |
| GET | /api/zones/{id}/scheduler-tasks/{taskId} | auth:sanctum | Статус scheduler-task по taskId (proxy к automation-engine) + `timeline` и outcome (`decision/reason_code`) |
| GET | /api/zones/{id}/telemetry/last | auth:sanctum | Последняя телеметрия |
| GET | /api/zones/{id}/telemetry/history| auth:sanctum | История телеметрии по метрикам |

Инварианты scheduler-task (`/api/zones/{id}/scheduler-tasks*`):
- terminal business-статусы: `completed|failed|rejected|expired`;
- transport-статусы scheduler уровня: `timeout|not_found` (только для lifecycle/diagnostics);
- `timeline[]` должен быть отсортирован по времени события по возрастанию.

---

## 4. Nodes

| Метод | Путь | Auth | Описание |
|-------|----------------------|------|-----------------------------------------------|
| GET | /api/nodes | auth:sanctum | Список узлов |
| POST | /api/nodes | auth:sanctum (operator/admin) | Зарегистрировать узел |
| GET | /api/nodes/{id} | auth:sanctum | Детали узла |
| PATCH | /api/nodes/{id} | auth:sanctum (operator/admin) | Обновить метаданные узла (name, zone_id) |
| DELETE| /api/nodes/{id} | auth:sanctum (admin) | Удалить узел |

Доп. действия:

| Метод | Путь | Auth | Описание |
|-------|------------------------------------|------|--------------------------------------------------|
| GET | /api/nodes/{id}/telemetry/last | auth:sanctum | Последняя телеметрия по узлу |
| GET | /api/nodes/{id}/config | auth:sanctum | Получить сохраненный NodeConfig (read-only) |
| POST | /api/nodes/{id}/commands | auth:sanctum (operator/admin) | Отправка низкоуровневых команд |
| PATCH | /api/node-channels/{id} | verify.python.service | Сервисное обновление `node_channels.config` (калибровки) |
| POST | /api/setup-wizard/validate-devices | auth:sanctum (operator/admin/agronomist/engineer) | Валидация обязательных ролей шага `4. Устройства` |
| POST | /api/setup-wizard/apply-device-bindings | auth:sanctum (operator/admin/agronomist/engineer) | Привязка ролей (`main_pump`, `drain`, `ph_*`, `ec_*`, `vent/heater/light`) к каналам выбранных нод |

---

## 5. Recipes

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /api/recipes | auth:sanctum | Список рецептов |
| POST | /api/recipes | auth:sanctum (operator/admin) | Создать рецепт |
| GET | /api/recipes/{id} | auth:sanctum | Детали рецепта |
| PATCH | /api/recipes/{id} | auth:sanctum (operator/admin) | Обновить рецепт |
| DELETE| /api/recipes/{id} | auth:sanctum (admin) | Удалить рецепт |

### Фазы рецептов

| Метод | Путь | Auth | Описание |
|-------|-------------------------------|------|------------------------------------|
| POST | /api/recipes/{id}/phases | auth:sanctum (operator/admin) | Добавить фазу |
| PATCH | /api/recipe-phases/{id} | auth:sanctum (operator/admin) | Обновить фазу |
| DELETE| /api/recipe-phases/{id} | auth:sanctum (admin) | Удалить фазу |

---

## 6. Telemetry / History

| Метод | Путь | Auth | Описание |
|-------|----------------------------------------------|------|-----------------------------------------------|
| GET | /api/zones/{id}/telemetry/last | auth:sanctum | Последние значения по зоне |
| GET | /api/zones/{id}/telemetry/history | auth:sanctum | История по зоне |
| GET | /api/nodes/{id}/telemetry/last | auth:sanctum | Последние значения по узлу |

---

## 7. Alerts / Events

| Метод | Путь | Auth | Описание |
|-------|------------------------------|------|-----------------------------------|
| GET | /api/alerts | auth:sanctum | Список алертов |
| GET | /api/alerts/{id} | auth:sanctum | Детали алерта |
| PATCH | /api/alerts/{id}/ack | auth:sanctum (operator/admin) | Подтвердить/принять алерт |
| GET | /api/alerts/stream | auth:sanctum | Server-Sent Events поток алертов |

---

## 8. Users (Admin only)

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /api/users | auth:sanctum (admin) | Список пользователей (фильтры: role, search) |
| POST | /api/users | auth:sanctum (admin) | Создать пользователя |
| GET | /api/users/{id} | auth:sanctum (admin) | Детали пользователя |
| PATCH | /api/users/{id} | auth:sanctum (admin) | Обновить пользователя (имя, email, пароль, роль) |
| DELETE| /api/users/{id} | auth:sanctum (admin) | Удалить пользователя |

---

## 8.1 User Preferences

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /settings/preferences | web auth | Получить пользовательские UI-настройки |
| PATCH | /settings/preferences | web auth | Обновить пользовательские UI-настройки |

Текущее поле:
- `alert_toast_suppression_sec` (0..600) — окно подавления повторных toast-уведомлений алертов.

---

## 9. System

| Метод | Путь | Auth | Описание |
|-------|---------------------------------|------|-------------------------------------------|
| GET | /api/system/config/full | public | Экспорт полной конфигурации (для Python сервисов) |
| GET | /api/system/health | public | Проверка здоровья сервиса |

---

## 10. Presets

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /api/presets | auth:sanctum | Список пресетов |
| POST | /api/presets | auth:sanctum (operator/admin) | Создать пресет |
| GET | /api/presets/{id} | auth:sanctum | Детали пресета |
| PATCH | /api/presets/{id} | auth:sanctum (operator/admin) | Обновить пресет |
| DELETE| /api/presets/{id} | auth:sanctum (admin) | Удалить пресет |

---

## 11. Reports & Analytics

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| GET | /api/recipes/{id}/analytics | auth:sanctum | Аналитика по рецепту |
| GET | /api/zones/{id}/harvests | auth:sanctum | История урожаев по зоне |
| POST | /api/harvests | auth:sanctum (operator/admin) | Регистрация урожая |
| POST | /api/recipes/comparison | auth:sanctum | Сравнение рецептов |

---

## 12. AI

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/ai/predict | auth:sanctum | Прогнозирование параметров |
| POST | /api/ai/explain_zone | auth:sanctum | Объяснение состояния зоны |
| POST | /api/ai/recommend | auth:sanctum | Рекомендации AI |
| POST | /api/ai/diagnostics | auth:sanctum | Диагностика системы |

---

## 13. Simulations (Digital Twin)

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/simulations/zone/{zone} | auth:sanctum (operator/admin) | Запуск симуляции |
| GET | /api/simulations/{job_id} | auth:sanctum | Статус симуляции + отчет |
| GET | /api/simulations/{simulation}/events | auth:sanctum | События процесса симуляции |
| GET | /api/simulations/{simulation}/events/stream | auth:sanctum | SSE-стрим событий симуляции |

---

## 14. Admin (минимальный CRUD)

| Метод | Путь | Auth | Описание |
|-------|----------------------------------------|------|-------------------------------------------|
| POST | /api/admin/zones/quick-create | auth:sanctum (admin) | Быстрое создание зоны |
| PATCH | /api/admin/recipes/{id}/quick-update | auth:sanctum (admin) | Быстрое обновление рецепта |

---

## 15. Python integration

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/python/ingest/telemetry | token-based | Инжест телеметрии из Python‑сервисов |
| POST | /api/python/commands/ack | token-based | ACK выполнения команд узлами |

---

## 16. Webhooks

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/alerts/webhook | public | Webhook от Alertmanager для создания алертов |

---

## 17. Правила расширения REST API для ИИ-агентов

1. **Не менять семантику существующих путей и HTTP-методов.**
2. Для принципиально новых возможностей — добавлять новые пути
 (или версию `/api/v2/ ` при необходимости).
3. Любой новый публичный эндпоинт должен быть:
 - описан здесь;
 - интегрирован в `API_SPEC_FRONTEND_BACKEND_FULL.md`;
 - покрыт базовыми тестами.
4. Все действия, влияющие на физическое оборудование,
 должны проходить через Python-сервис, а не напрямую в MQTT.

Этот документ должен использоваться как **справочник** и основа для автодокументации (например, Swagger).

---

## 18. Internal Python Services (service-to-service)

### 18.1 Automation-engine health endpoints

| Метод | Путь | Auth | Описание |
|-------|----------------------|------|----------------------------------------------|
| GET | /health/live | internal | Liveness: процесс API доступен |
| GET | /health/ready | internal | Readiness: `CommandBus`, DB и bootstrap lease-store готовы |

### 18.2 Automation-engine scheduler endpoints

| Метод | Путь | Auth | Описание |
|-------|-------------------------------|------|----------------------------------------------------|
| POST | /scheduler/bootstrap | internal | Startup-handshake scheduler -> automation-engine |
| POST | /scheduler/bootstrap/heartbeat | internal | Heartbeat/lease keepalive для scheduler |
| POST | /scheduler/task | internal | Принять task intent от scheduler |
| GET | /scheduler/task/{task_id} | internal | Получить task status/outcome |
| POST | /scheduler/internal/enqueue | internal | Внутренний enqueue self-task (AE -> scheduler) |

Инварианты task-level API (`POST /scheduler/task`):
- обязательны `correlation_id`, `due_at`, `expires_at`;
- идемпотентность по `correlation_id` + `idempotency_payload_mismatch` при mismatch payload;
- успех execute-пути считается подтвержденным только при статусе ноды `DONE`.
