# Changelog - Backend Services

## 2025-11-21

### Исправления

#### Привязка рецептов к зонам
- **Проблема:** Рецепт не отображался на фронтенде после привязки
- **Причина:** Несоответствие формата данных (snake_case vs camelCase) между Laravel и Vue.js
- **Решение:**
  - Добавлена нормализация `recipe_instance` → `recipeInstance` в computed свойстве `zone`
  - Улучшена загрузка `recipeInstance` с связанным `recipe` в web-роуте
  - Исправлена обработка данных после привязки рецепта через API
- **Файлы:** `backend/laravel/resources/js/Pages/Zones/Show.vue`, `backend/laravel/routes/web.php`

#### Логирование
- Исправлено использование `logger.info` - добавлены безопасные обёртки
- Файлы: `backend/laravel/resources/js/Components/AttachRecipeModal.vue`, `backend/laravel/resources/js/Pages/Zones/Show.vue`

#### Мониторинг
- Исправлены порты для метрик Prometheus (history-logger: 9300)
- См. `PROMETHEUS_FIX_SUMMARY.md` для деталей

### Улучшения

#### Setup Wizard
- Добавлена возможность выбора существующих теплиц и зон
- Улучшен UX мастера настройки
- Файлы: `backend/laravel/resources/js/Pages/Setup/Wizard.vue`

#### UI Components
- Созданы компоненты для привязки рецептов и узлов к зонам
- Улучшено отображение состояния рецептов на странице зоны
- Файлы: `backend/laravel/resources/js/Components/AttachRecipeModal.vue`, `backend/laravel/resources/js/Components/AttachNodesModal.vue`

---

_Подробные отчеты об исправлениях см. в `docs/fixes/` (после консолидации)_

