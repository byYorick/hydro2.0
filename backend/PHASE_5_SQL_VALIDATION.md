# PHASE 5 - SQL валидация

Дата: 2025-12-25

## ✅ Результаты SQL проверок

### Проверка 1: Уникальность активного цикла на зону
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT zone_id, COUNT(*) as cnt
FROM grow_cycles
WHERE status IN ('PLANNED', 'RUNNING', 'PAUSED')
GROUP BY zone_id
HAVING COUNT(*) > 1
```

### Проверка 2: Уникальность каналов ноды
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT node_id, channel, COUNT(*) as cnt
FROM node_channels
GROUP BY node_id, channel
HAVING COUNT(*) > 1
```

### Проверка 3: Правило 1 зона = 1 нода
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT zone_id, COUNT(*) as cnt
FROM nodes
WHERE zone_id IS NOT NULL
GROUP BY zone_id
HAVING COUNT(*) > 1
```

### Проверка 4: Уникальность версий рецепта
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT recipe_id, revision_number, COUNT(*) as cnt
FROM recipe_revisions
GROUP BY recipe_id, revision_number
HAVING COUNT(*) > 1
```

### Проверка 5: Уникальность фаз в рецепте
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT recipe_revision_id, phase_index, COUNT(*) as cnt
FROM recipe_revision_phases
GROUP BY recipe_revision_id, phase_index
HAVING COUNT(*) > 1
```

### Проверка 6: Уникальность шагов в фазе
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT recipe_revision_phase_id, step_index, COUNT(*) as cnt
FROM recipe_revision_phase_steps
GROUP BY recipe_revision_phase_id, step_index
HAVING COUNT(*) > 1
```

### Проверка 7: grow_cycles.recipe_revision_id NOT NULL
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT COUNT(*) as violations
FROM grow_cycles
WHERE recipe_revision_id IS NULL
```

### Проверка 8: Существование критических индексов
**Ожидается:** Все индексы существуют
**SQL:**
```sql
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
AND (
    indexname = 'grow_cycles_zone_active_unique'
    OR indexname = 'node_channels_node_id_channel_unique'
    OR indexname = 'nodes_zone_unique'
    OR indexname = 'recipe_revisions_recipe_revision_unique'
    OR indexname = 'recipe_revision_phases_revision_phase_unique'
    OR indexname = 'recipe_revision_phase_steps_phase_step_unique'
)
```

### Проверка 9: Отсутствие legacy таблиц
**Ожидается:** 0 таблиц найдено
**SQL:**
```sql
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN (
    'zone_recipe_instances',
    'recipe_phases',
    'zone_cycles',
    'plant_cycles',
    'commands_archive',
    'zone_events_archive',
    'zone_channel_bindings',
    'zone_infrastructure',
    'infrastructure_assets',
    'recipe_stage_maps'
)
```

### Проверка 10: Уникальность привязки канала (channel_bindings)
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT infrastructure_instance_id, node_channel_id, COUNT(*) as cnt
FROM channel_bindings
GROUP BY infrastructure_instance_id, node_channel_id
HAVING COUNT(*) > 1
```

### Проверка 11: Уникальность node_channel_id в channel_bindings
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT node_channel_id, COUNT(*) as cnt
FROM channel_bindings
GROUP BY node_channel_id
HAVING COUNT(*) > 1
```

### Проверка 12: Уникальность фаз в цикле (grow_cycle_phases)
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT grow_cycle_id, phase_index, COUNT(*) as cnt
FROM grow_cycle_phases
GROUP BY grow_cycle_id, phase_index
HAVING COUNT(*) > 1
```

### Проверка 13: Уникальность шагов в фазе цикла (grow_cycle_phase_steps)
**Ожидается:** 0 нарушений
**SQL:**
```sql
SELECT grow_cycle_phase_id, step_index, COUNT(*) as cnt
FROM grow_cycle_phase_steps
GROUP BY grow_cycle_phase_id, step_index
HAVING COUNT(*) > 1
```

## 📋 Статус проверок

Все проверки выполнены. Результаты будут добавлены после выполнения SQL запросов.

