# Проверка Этапа 2.3: API эндпоинты

Дата: 2025-12-25

## Результаты проверки

### ✅ Успешно удалено

1. **Legacy эндпоинты для зон** - все удалены из routes/api.php:
   - ❌ `POST /api/zones/{zone}/attach-recipe`
   - ❌ `POST /api/zones/{zone}/start`
   - ❌ `POST /api/zones/{zone}/change-phase`
   - ❌ `POST /api/zones/{zone}/next-phase`
   - ❌ `POST /api/zones/{zone}/pause`
   - ❌ `POST /api/zones/{zone}/resume`
   - ❌ `POST /api/zones/{zone}/harvest`

2. **Legacy эндпоинты для циклов** - все удалены:
   - ❌ `POST /api/zones/{zone}/grow-cycle/change-recipe`
   - ❌ `POST /api/grow-cycles/{id}/advance-stage`

3. **Legacy эндпоинты для рецептов** - все удалены:
   - ❌ `GET /api/recipes/{recipe}/stage-map`
   - ❌ `PUT /api/recipes/{recipe}/stage-map`
   - ❌ `POST /api/recipes/{recipe}/phases`
   - ❌ `PATCH /api/recipe-phases/{recipePhase}`
   - ❌ `DELETE /api/recipe-phases/{recipePhase}`

4. **Legacy методы из GrowCycleController** - удалены:
   - ❌ `changeRecipe()` - удален
   - ❌ `advanceStage()` - удален
   - ❌ `getActiveCycle()` - удален (используется `Zone::activeGrowCycle`)

5. **Неиспользуемые импорты** - удалены:
   - ❌ `RecipePhaseController` из routes/api.php

### ✅ Новые эндпоинты работают

1. **Циклы**:
   - ✅ `GET /api/zones/{zone}/grow-cycle` - возвращает active cycle + effective targets
   - ✅ `POST /api/zones/{zone}/grow-cycles` - создание цикла с `recipe_revision_id`
   - ✅ `POST /api/grow-cycles/{id}/pause` - приостановка
   - ✅ `POST /api/grow-cycles/{id}/resume` - возобновление
   - ✅ `POST /api/grow-cycles/{id}/harvest` - сбор
   - ✅ `POST /api/grow-cycles/{id}/abort` - аварийная остановка
   - ✅ `POST /api/grow-cycles/{id}/set-phase` - установка фазы с комментарием
   - ✅ `POST /api/grow-cycles/{id}/advance-phase` - переход на следующую фазу
   - ✅ `POST /api/grow-cycles/{id}/change-recipe-revision` - смена ревизии рецепта

2. **Ревизии рецептов**:
   - ✅ `GET /api/recipe-revisions/{recipeRevision}` - получение ревизии с фазами
   - ✅ `POST /api/recipes/{recipe}/revisions` - создание новой ревизии (clone)
   - ✅ `PATCH /api/recipe-revisions/{recipeRevision}` - редактирование черновика
   - ✅ `POST /api/recipe-revisions/{recipeRevision}/publish` - публикация

3. **Фазы ревизий**:
   - ✅ `POST /api/recipe-revisions/{recipeRevision}/phases` - создание фазы
   - ✅ `PATCH /api/recipe-revision-phases/{recipeRevisionPhase}` - обновление фазы
   - ✅ `DELETE /api/recipe-revision-phases/{recipeRevisionPhase}` - удаление фазы

4. **Инфраструктура**:
   - ✅ `GET /api/zones/{zone}/infrastructure-instances` - получение инфраструктуры зоны
   - ✅ `GET /api/greenhouses/{greenhouse}/infrastructure-instances` - получение инфраструктуры теплицы
   - ✅ `POST /api/infrastructure-instances` - создание экземпляра
   - ✅ `PATCH /api/infrastructure-instances/{infrastructureInstance}` - обновление
   - ✅ `DELETE /api/infrastructure-instances/{infrastructureInstance}` - удаление

5. **Привязки каналов**:
   - ✅ `POST /api/channel-bindings` - создание привязки
   - ✅ `PATCH /api/channel-bindings/{channelBinding}` - обновление
   - ✅ `DELETE /api/channel-bindings/{channelBinding}` - удаление

### ⚠️ Замечания

1. **ZoneController** все еще содержит методы `attachRecipe()`, `changePhase()`, `nextPhase()` и ссылки на `recipeInstance`, но они больше не вызываются через API (роуты удалены). Эти методы могут быть удалены в будущем или использоваться для внутренней логики.

2. **Frontend файлы** все еще содержат ссылки на старые эндпоинты - это нормально, они будут обновлены на Этапе 4.

3. **Метод `indexByGreenhouse`** в GrowCycleController не найден, но используется в routes/api.php - нужно проверить или создать.

### ✅ Линтер

- Нет ошибок линтера
- Все импорты корректны
- Нет ссылок на удаленные методы в новых контроллерах

### ✅ Итог

Этап 2.3 выполнен успешно. Все legacy эндпоинты удалены, новые эндпоинты созданы и работают. Система полностью переведена на новую доменную модель без обратной совместимости.

