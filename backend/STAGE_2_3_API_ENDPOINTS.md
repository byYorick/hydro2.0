# Этап 2.3: API эндпоинты (перепроектирование)

Дата: 2025-12-25

## Выполнено

### 1. Новые контроллеры

#### RecipeRevisionController
- `GET /api/recipe-revisions/{recipeRevision}` - Получить ревизию с фазами
- `POST /api/recipes/{recipe}/revisions` - Создать новую ревизию (clone или пустую)
- `PATCH /api/recipe-revisions/{recipeRevision}` - Редактировать черновик ревизии
- `POST /api/recipe-revisions/{recipeRevision}/publish` - Опубликовать ревизию (lock)

#### RecipeRevisionPhaseController
- `POST /api/recipe-revisions/{recipeRevision}/phases` - Создать фазу в ревизии
- `PATCH /api/recipe-revision-phases/{recipeRevisionPhase}` - Обновить фазу
- `DELETE /api/recipe-revision-phases/{recipeRevisionPhase}` - Удалить фазу

#### InfrastructureInstanceController
- `GET /api/zones/{zone}/infrastructure-instances` - Получить инфраструктуру зоны
- `GET /api/greenhouses/{greenhouse}/infrastructure-instances` - Получить инфраструктуру теплицы
- `POST /api/infrastructure-instances` - Создать экземпляр инфраструктуры
- `PATCH /api/infrastructure-instances/{infrastructureInstance}` - Обновить экземпляр
- `DELETE /api/infrastructure-instances/{infrastructureInstance}` - Удалить экземпляр

#### ChannelBindingController
- `POST /api/channel-bindings` - Создать привязку канала
- `PATCH /api/channel-bindings/{channelBinding}` - Обновить привязку
- `DELETE /api/channel-bindings/{channelBinding}` - Удалить привязку

### 2. Обновленные методы GrowCycleController

#### Новые методы
- `GET /api/zones/{zone}/grow-cycle` - Получить активный цикл с effective targets и прогрессом
- `POST /api/zones/{zone}/grow-cycles` - Создать новый цикл (требует `recipe_revision_id` и `plant_id`)
- `POST /api/grow-cycles/{id}/set-phase` - Установить конкретную фазу (manual switch с комментарием)
- `POST /api/grow-cycles/{id}/advance-phase` - Переход на следующую фазу
- `POST /api/grow-cycles/{id}/change-recipe-revision` - Сменить ревизию рецепта (apply now / at next phase)

#### Существующие методы (обновлены)
- `POST /api/grow-cycles/{id}/pause` - Приостановить цикл
- `POST /api/grow-cycles/{id}/resume` - Возобновить цикл
- `POST /api/grow-cycles/{id}/harvest` - Зафиксировать сбор
- `POST /api/grow-cycles/{id}/abort` - Аварийная остановка

### 3. Legacy эндпоинты (помечены как deprecated)

Следующие эндпоинты помечены как legacy, но оставлены для совместимости:
- `POST /api/zones/{zone}/attach-recipe` → Используйте `POST /api/zones/{zone}/grow-cycles`
- `POST /api/zones/{zone}/grow-cycle/change-recipe` → Используйте `POST /api/grow-cycles/{id}/change-recipe-revision`
- `POST /api/grow-cycles/{id}/advance-stage` → Используйте `POST /api/grow-cycles/{id}/advance-phase`
- `POST /api/recipes/{recipe}/phases` → Используйте `POST /api/recipe-revisions/{recipeRevision}/phases`
- `PUT /api/recipes/{recipe}/stage-map` → Используйте `recipe_revision_phases.stage_template_id`

### 4. Ключевые изменения в логике

#### Создание цикла
- Теперь требует `recipe_revision_id` вместо `recipe_id`
- Проверяет, что ревизия имеет статус `PUBLISHED`
- Автоматически устанавливает первую фазу ревизии
- Проверяет уникальность активного цикла в зоне

#### Управление фазами
- Все переходы фаз логируются в `grow_cycle_transitions`
- События также записываются в `zone_events`
- WebSocket broadcast отправляется при каждом изменении цикла

#### Ревизии рецептов
- Только `DRAFT` ревизии можно редактировать
- Только `PUBLISHED` ревизии можно использовать для циклов
- Клонирование ревизий включает все фазы и подшаги

### 5. Интеграция с EffectiveTargetsService

Метод `GET /api/zones/{zone}/grow-cycle` теперь возвращает:
- Данные цикла
- Effective targets текущей фазы (с учетом overrides)
- Прогресс фазы

### 6. Валидация и проверки

#### Ревизии рецептов
- При публикации проверяется наличие хотя бы одной фазы
- При создании цикла проверяется статус ревизии

#### Циклы
- Проверка уникальности активного цикла в зоне
- Проверка наличия фаз в ревизии перед созданием цикла
- Проверка доступа к зоне для всех операций

#### Инфраструктура
- Проверка доступа к зоне/теплице перед операциями
- Валидация типов активов (PUMP, MISTER, TANK_CLEAN, и т.д.)

## Следующие шаги

1. **Этап 2.4**: Настроить права доступа (только agronomist может управлять циклами)
2. **Этап 2.5**: Обновить события и логи (уже частично реализовано)
3. **Этап 3.1**: Создать batch-endpoint для effective targets

## Примечания

- Все legacy эндпоинты помечены как deprecated, но продолжают работать
- Новые эндпоинты используют новую доменную модель (GrowCycle → RecipeRevision → RecipeRevisionPhase)
- Effective targets интегрированы в основной эндпоинт получения цикла

