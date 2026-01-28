-- telemetry_retention.sql
-- Политики хранения данных телеметрии
-- Raw данные: 90 дней, агрегаты: 1 год

-- Функция для удаления старых партиций (вызывается из job'а)
CREATE OR REPLACE FUNCTION cleanup_old_telemetry_partitions()
RETURNS INTEGER AS $$
DECLARE
    partition_name TEXT;
    partition_date DATE;
    deleted_count INTEGER := 0;
    retention_days INTEGER := 90; -- Raw данные храним 90 дней
BEGIN
    -- Находим все партиции старше retention_days дней
    FOR partition_name IN
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename LIKE 'telemetry_samples_%'
    LOOP
        -- Извлекаем дату из имени партиции (telemetry_samples_YYYY_MM)
        BEGIN
            partition_date := TO_DATE(
                SUBSTRING(partition_name FROM 'telemetry_samples_(\d{4}_\d{2})'),
                'YYYY_MM'
            );
            
            -- Если партиция старше retention_days дней, удаляем её
            IF partition_date < CURRENT_DATE - (retention_days || ' days')::INTERVAL THEN
                EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', partition_name);
                deleted_count := deleted_count + 1;
                RAISE NOTICE 'Deleted partition: %', partition_name;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Игнорируем партиции с неправильным форматом имени
            CONTINUE;
        END;
    END LOOP;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Комментарии
COMMENT ON FUNCTION cleanup_old_telemetry_partitions IS 'Удаляет партиции telemetry_samples старше 90 дней';

-- Пример вызова (должен выполняться из cron job или Laravel scheduler):
-- SELECT cleanup_old_telemetry_partitions();

