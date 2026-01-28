-- Проверочный SQL скрипт для миграции unassigned_node_errors
-- Запустить после применения миграций

-- 1. Проверка существования таблицы
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'unassigned_node_errors'
) AS table_exists;

-- 2. Проверка колонок
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'unassigned_node_errors'
ORDER BY ordinal_position;

-- 3. Проверка индексов
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'unassigned_node_errors'
ORDER BY indexname;

-- 4. Тест вставки с NULL error_code
INSERT INTO unassigned_node_errors (
    hardware_id, error_message, error_code, severity, topic,
    count, first_seen_at, last_seen_at
) VALUES (
    'test-null-code-1', 'Test error', NULL, 'ERROR', 'test/topic',
    1, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- 5. Тест вставки с error_code
INSERT INTO unassigned_node_errors (
    hardware_id, error_message, error_code, severity, topic,
    count, first_seen_at, last_seen_at
) VALUES (
    'test-with-code-1', 'Test error', 'ERR_TEST', 'ERROR', 'test/topic',
    1, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- 6. Проверка уникального ограничения (должна вызвать ошибку при дубликате)
-- Это должно вызвать ошибку:
-- INSERT INTO unassigned_node_errors (
--     hardware_id, error_message, error_code, severity, topic,
--     count, first_seen_at, last_seen_at
-- ) VALUES (
--     'test-with-code-1', 'Another error', 'ERR_TEST', 'WARNING', 'test/topic2',
--     1, NOW(), NOW()
-- );

-- 7. Очистка тестовых данных
DELETE FROM unassigned_node_errors 
WHERE hardware_id LIKE 'test-%';

