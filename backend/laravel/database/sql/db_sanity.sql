-- db_sanity.sql
-- Проверка ключевых инвариантов БД после миграций
-- Использование: psql -d hydro2 -f db_sanity.sql

-- ============================================
-- 1. Проверка уникальности активного цикла на зону
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT zone_id, COUNT(*) as cnt
        FROM grow_cycles
        WHERE status IN ('PLANNED', 'RUNNING', 'PAUSED')
        GROUP BY zone_id
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % зон с более чем одним активным циклом', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Уникальность активного цикла на зону соблюдена';
END $$;

-- ============================================
-- 2. Проверка 1:1 зона↔нода
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    -- Проверка: одна зона не может иметь несколько нод
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT zone_id, COUNT(*) as cnt
        FROM nodes
        WHERE zone_id IS NOT NULL
        GROUP BY zone_id
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % зон с более чем одной нодой', violation_count;
    END IF;
    
    -- Проверка: одна нода не может быть привязана к нескольким зонам
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT node_id, COUNT(*) as cnt
        FROM zones
        WHERE node_id IS NOT NULL
        GROUP BY node_id
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % нод, привязанных к более чем одной зоне', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Правило 1:1 зона↔нода соблюдено';
END $$;

-- ============================================
-- 3. Проверка NOT NULL для recipe_revision_id
-- ============================================
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM grow_cycles
    WHERE recipe_revision_id IS NULL;
    
    IF null_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % циклов с NULL recipe_revision_id', null_count;
    END IF;
    
    RAISE NOTICE 'OK: Все циклы имеют recipe_revision_id';
END $$;

-- ============================================
-- 4. Проверка уникальности каналов ноды
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT node_id, channel, COUNT(*) as cnt
        FROM node_channels
        GROUP BY node_id, channel
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % дубликатов каналов в нодах', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Уникальность каналов ноды соблюдена';
END $$;

-- ============================================
-- 5. Проверка нормализации channel_bindings через node_channel_id
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    -- Проверка: все channel_bindings должны иметь node_channel_id
    SELECT COUNT(*) INTO violation_count
    FROM channel_bindings
    WHERE node_channel_id IS NULL;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % channel_bindings без node_channel_id', violation_count;
    END IF;
    
    -- Проверка: один канал не может быть привязан к нескольким инстансам
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT node_channel_id, COUNT(*) as cnt
        FROM channel_bindings
        GROUP BY node_channel_id
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % каналов, привязанных к нескольким инстансам', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Нормализация channel_bindings соблюдена';
END $$;

-- ============================================
-- 6. Проверка упорядочивания фаз рецепта
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT recipe_revision_id, phase_index, COUNT(*) as cnt
        FROM recipe_revision_phases
        GROUP BY recipe_revision_id, phase_index
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % дубликатов фаз в ревизиях рецептов', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Упорядочивание фаз рецепта соблюдено';
END $$;

-- ============================================
-- 7. Проверка упорядочивания шагов фазы
-- ============================================
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM (
        SELECT phase_id, step_index, COUNT(*) as cnt
        FROM recipe_revision_phase_steps
        GROUP BY phase_id, step_index
        HAVING COUNT(*) > 1
    ) violations;
    
    IF violation_count > 0 THEN
        RAISE EXCEPTION 'VIOLATION: Найдено % дубликатов шагов в фазах', violation_count;
    END IF;
    
    RAISE NOTICE 'OK: Упорядочивание шагов фазы соблюдено';
END $$;

-- ============================================
-- 8. Проверка отсутствия JSON в базовых полях шагов
-- ============================================
DO $$
DECLARE
    json_count INTEGER;
BEGIN
    -- Проверка: targets_override должен быть NULL или удалён
    SELECT COUNT(*) INTO json_count
    FROM recipe_revision_phase_steps
    WHERE targets_override IS NOT NULL;
    
    IF json_count > 0 THEN
        RAISE WARNING 'WARNING: Найдено % шагов с targets_override (должно быть NULL или колонками)', json_count;
    ELSE
        RAISE NOTICE 'OK: Базовые параметры шагов хранятся колонками, не JSON';
    END IF;
END $$;

-- ============================================
-- 9. Проверка наличия статуса AWAITING_CONFIRM
-- ============================================
DO $$
DECLARE
    status_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'grow_cycles'
        AND column_name = 'status'
        AND data_type = 'USER-DEFINED'
    ) INTO status_exists;
    
    IF status_exists THEN
        -- Проверка через enum значения
        PERFORM 1 FROM pg_enum 
        WHERE enumlabel = 'AWAITING_CONFIRM' 
        AND enumtypid = (
            SELECT oid FROM pg_type WHERE typname = 'grow_cycle_status'
        );
        
        IF NOT FOUND THEN
            RAISE EXCEPTION 'VIOLATION: Статус AWAITING_CONFIRM не найден в enum grow_cycle_status';
        END IF;
        
        RAISE NOTICE 'OK: Статус AWAITING_CONFIRM присутствует';
    ELSE
        RAISE WARNING 'WARNING: Не удалось проверить статус AWAITING_CONFIRM (возможно используется string)';
    END IF;
END $$;

-- ============================================
-- 10. Проверка индексов
-- ============================================
DO $$
DECLARE
    index_exists BOOLEAN;
BEGIN
    -- Проверка partial unique index для активных циклов
    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE indexname = 'grow_cycles_zone_active_unique'
    ) INTO index_exists;
    
    IF NOT index_exists THEN
        RAISE EXCEPTION 'VIOLATION: Индекс grow_cycles_zone_active_unique не найден';
    END IF;
    
    RAISE NOTICE 'OK: Partial unique index для активных циклов существует';
    
    -- Проверка индекса для 1:1 зона↔нода
    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE indexname IN ('nodes_zone_unique', 'zones_node_unique')
    ) INTO index_exists;
    
    IF NOT index_exists THEN
        RAISE WARNING 'WARNING: Индекс для 1:1 зона↔нода не найден';
    ELSE
        RAISE NOTICE 'OK: Индекс для 1:1 зона↔нода существует';
    END IF;
END $$;

-- ============================================
-- Итоговый результат
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Все проверки инвариантов пройдены успешно!';
    RAISE NOTICE '========================================';
END $$;

