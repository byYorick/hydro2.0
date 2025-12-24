-- Миграция для поддержки Circuit Breaker, Command Tracking и PID State

-- Таблица для сохранения состояния PID контроллеров
CREATE TABLE IF NOT EXISTS pid_state (
    zone_id INTEGER NOT NULL,
    pid_type VARCHAR(10) NOT NULL CHECK (pid_type IN ('ph', 'ec')),
    integral FLOAT NOT NULL DEFAULT 0.0,
    prev_error FLOAT,
    last_output_ms BIGINT NOT NULL DEFAULT 0,
    stats JSONB,
    current_zone VARCHAR(20),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (zone_id, pid_type),
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pid_state_zone_id ON pid_state(zone_id);
CREATE INDEX IF NOT EXISTS idx_pid_state_updated_at ON pid_state(updated_at);

-- Таблица для отслеживания команд
CREATE TABLE IF NOT EXISTS command_tracking (
    id SERIAL PRIMARY KEY,
    cmd_id VARCHAR(100) NOT NULL UNIQUE,
    zone_id INTEGER NOT NULL,
    command JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    response JSONB,
    error TEXT,
    latency_seconds FLOAT,
    context JSONB,
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_command_tracking_zone_id ON command_tracking(zone_id);
CREATE INDEX IF NOT EXISTS idx_command_tracking_status ON command_tracking(status);
CREATE INDEX IF NOT EXISTS idx_command_tracking_sent_at ON command_tracking(sent_at);
CREATE INDEX IF NOT EXISTS idx_command_tracking_cmd_id ON command_tracking(cmd_id);

-- Таблица для аудита команд
CREATE TABLE IF NOT EXISTS command_audit (
    id SERIAL PRIMARY KEY,
    zone_id INTEGER NOT NULL,
    command_type VARCHAR(50) NOT NULL,
    command_data JSONB NOT NULL,
    telemetry_snapshot JSONB,
    decision_context JSONB,
    pid_state JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_command_audit_zone_id ON command_audit(zone_id);
CREATE INDEX IF NOT EXISTS idx_command_audit_created_at ON command_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_command_audit_command_type ON command_audit(command_type);

-- Комментарии к таблицам
COMMENT ON TABLE pid_state IS 'Состояние PID контроллеров для восстановления после перезапуска';
COMMENT ON TABLE command_tracking IS 'Отслеживание выполнения команд с подтверждениями';
COMMENT ON TABLE command_audit IS 'Полный аудит всех команд для прозрачности системы';


