-- telemetry_partitioning.sql
-- Настройка партиционирования для telemetry_samples по месяцам
-- Выполняется после создания таблицы telemetry_samples

-- Создаём функцию для автоматического создания партиций
CREATE OR REPLACE FUNCTION create_telemetry_partition(partition_date DATE)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    -- Формируем имя партиции: telemetry_samples_YYYY_MM
    partition_name := 'telemetry_samples_' || TO_CHAR(partition_date, 'YYYY_MM');
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';
    
    -- Проверяем, существует ли партиция
    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = partition_name
    ) THEN
        -- Создаём партицию
        EXECUTE format('
            CREATE TABLE %I PARTITION OF telemetry_samples
            FOR VALUES FROM (%L) TO (%L)
        ', partition_name, start_date, end_date);
        
        -- Создаём индексы для партиции
        EXECUTE format('CREATE INDEX %I ON %I (sensor_id, ts)', 
            partition_name || '_sensor_ts_idx', partition_name);
        EXECUTE format('CREATE INDEX %I ON %I (zone_id, ts)', 
            partition_name || '_zone_ts_idx', partition_name);
        EXECUTE format('CREATE INDEX %I ON %I (cycle_id, ts)', 
            partition_name || '_cycle_ts_idx', partition_name);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Создаём партиции на 3 месяца вперёд и 1 месяц назад
SELECT create_telemetry_partition(CURRENT_DATE - INTERVAL '1 month');
SELECT create_telemetry_partition(CURRENT_DATE);
SELECT create_telemetry_partition(CURRENT_DATE + INTERVAL '1 month');
SELECT create_telemetry_partition(CURRENT_DATE + INTERVAL '2 months');
SELECT create_telemetry_partition(CURRENT_DATE + INTERVAL '3 months');

-- Создаём функцию для автоматического создания партиций (вызывается из job'а)
CREATE OR REPLACE FUNCTION ensure_telemetry_partitions()
RETURNS VOID AS $$
DECLARE
    months_ahead INTEGER := 3;
    i INTEGER;
BEGIN
    FOR i IN 0..months_ahead LOOP
        PERFORM create_telemetry_partition(CURRENT_DATE + (i || ' months')::INTERVAL);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Комментарии
COMMENT ON FUNCTION create_telemetry_partition IS 'Создаёт партицию для telemetry_samples на указанный месяц';
COMMENT ON FUNCTION ensure_telemetry_partitions IS 'Обеспечивает наличие партиций на ближайшие месяцы';

