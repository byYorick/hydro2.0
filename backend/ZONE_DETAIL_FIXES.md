# Исправления Zone Detail Page

## Исправленные проблемы

### 1. ✅ Захардкоженные параметры команд
**Проблема**: `onRunCycle` отправлял команды с пустым объектом `{}` вместо использования параметров из targets/recipe.

**Решение**: 
- Добавлена функция `getDefaultCycleParams()` которая получает параметры из:
  1. `targets` (если доступны)
  2. Текущей фазы рецепта (`recipeInstance.current_phase_index`)
  3. Значений по умолчанию (fallback)

**Параметры для каждого типа цикла**:
- **IRRIGATION**: `duration_sec` из `targets.irrigation_duration_sec` или `recipePhase.targets.irrigation_duration_sec` (по умолчанию: 10 сек)
- **PH_CONTROL**: `target_ph` из `targets.ph` или `recipePhase.targets.ph` (по умолчанию: 6.0)
- **EC_CONTROL**: `target_ec` из `targets.ec` или `recipePhase.targets.ec` (по умолчанию: 1.5)
- **CLIMATE**: `target_temp` и `target_humidity` из `targets` или `recipePhase.targets` (по умолчанию: 22°C, 60%)
- **LIGHTING**: `duration_hours` и `intensity` из `targets.light_hours` или `recipePhase.targets.light_hours` (по умолчанию: 12 часов, 80%)

### 2. ✅ Обработка ошибок
**Проблема**: Ошибки при отправке команд не обрабатывались централизованно.

**Решение**: 
- Добавлен `useErrorHandler` для централизованной обработки ошибок
- Ошибки логируются и показываются пользователю через toast-уведомления

### 3. ✅ Обновление состояния
**Проблема**: Использование `window.location.reload()` теряло состояние и ломало UX.

**Решение**: 
- Используется `router.reload({ only })` из Inertia.js для partial reload
- Обновляются только необходимые props (`zone`, `cycles`), состояние сохраняется

## Измененные файлы

- `backend/laravel/resources/js/Pages/Zones/Show.vue`

## Результат

Теперь Zone Detail работает корректно:
- ✅ Параметры команд берутся из targets/recipe, а не захардкожены
- ✅ Ошибки обрабатываются централизованно с уведомлениями
- ✅ Состояние сохраняется при обновлении данных (partial reload)
- ✅ Команды отправляются с правильными параметрами из текущей фазы рецепта

## Дополнительные улучшения

1. **Логирование**: Добавлено подробное логирование параметров команд для отладки
2. **Fallback значения**: Если параметры не найдены в targets/recipe, используются разумные значения по умолчанию
3. **Типизация**: Добавлены типы для всех параметров команд

