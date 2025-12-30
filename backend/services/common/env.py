import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = os.getenv("MQTT_HOST", "mqtt")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_client_id: str = os.getenv("MQTT_CLIENT_ID", "hydro-core")
    mqtt_clean_session: bool = os.getenv("MQTT_CLEAN_SESSION", "0") == "1"
    mqtt_user: str | None = os.getenv("MQTT_USER")
    mqtt_pass: str | None = os.getenv("MQTT_PASS")
    # По умолчанию TLS выключен для dev окружения (можно включить через MQTT_TLS=1)
    # В продакшене TLS должен быть включен
    mqtt_tls: bool = os.getenv("MQTT_TLS", "0") in ("1", "true", "True", "yes", "Yes")
    mqtt_ca_file: str | None = os.getenv("MQTT_CA_FILE")

    pg_host: str = os.getenv("PG_HOST", "db")
    pg_port: int = int(os.getenv("PG_PORT", "5432"))
    pg_db: str = os.getenv("PG_DB", "hydro_dev")
    pg_user: str = os.getenv("PG_USER", "hydro")
    # Пароль БД обязателен в продакшене (не используем дефолтный "hydro")
    pg_pass: str = os.getenv("PG_PASS") or os.getenv("POSTGRES_PASSWORD") or ""

    laravel_api_url: str = os.getenv("LARAVEL_API_URL", "http://laravel")
    laravel_api_token: str = os.getenv("LARAVEL_API_TOKEN", "")
    bridge_api_token: str = os.getenv("PY_API_TOKEN", "")
    # Для ingest операций (регистрация нод, телеметрия) используем PY_INGEST_TOKEN
    ingest_token: str = os.getenv("PY_INGEST_TOKEN", "") or os.getenv("PY_API_TOKEN", "")
    history_logger_api_token: str = os.getenv("HISTORY_LOGGER_API_TOKEN", "") or os.getenv("PY_INGEST_TOKEN", "") or os.getenv("PY_API_TOKEN", "")  # Используем PY_INGEST_TOKEN как основной fallback

    telemetry_batch_size: int = int(os.getenv("TELEMETRY_BATCH_SIZE", "1000"))  # Увеличено для высокой нагрузки
    telemetry_flush_ms: int = int(os.getenv("TELEMETRY_FLUSH_MS", "200"))  # Уменьшено для быстрой обработки
    realtime_queue_max_size: int = int(os.getenv("REALTIME_QUEUE_MAX_SIZE", "5000"))
    realtime_flush_ms: int = int(os.getenv("REALTIME_FLUSH_MS", "500"))
    realtime_batch_max_updates: int = int(os.getenv("REALTIME_BATCH_MAX_UPDATES", "200"))
    command_timeout_sec: int = int(os.getenv("COMMAND_TIMEOUT_SEC", "30"))
    mqtt_zone_format: str = os.getenv("MQTT_ZONE_FORMAT", "id")  # id | uid
    service_port: int = int(os.getenv("SERVICE_PORT", "9300"))  # Порт для history-logger
    node_default_secret: str = os.getenv("NODE_DEFAULT_SECRET", "hydro-default-secret-key-2025")
    
    # History Logger specific settings
    shutdown_wait_sec: int = int(os.getenv("SHUTDOWN_WAIT_SEC", "2"))  # Время ожидания перед закрытием Redis
    shutdown_timeout_sec: float = float(os.getenv("SHUTDOWN_TIMEOUT_SEC", "30.0"))  # Таймаут graceful shutdown
    final_batch_multiplier: int = int(os.getenv("FINAL_BATCH_MULTIPLIER", "10"))  # Множитель для финального батча
    queue_check_interval_sec: float = float(os.getenv("QUEUE_CHECK_INTERVAL_SEC", "0.05"))  # Уменьшено для быстрой реакции (50ms)
    queue_error_retry_delay_sec: float = float(os.getenv("QUEUE_ERROR_RETRY_DELAY_SEC", "1.0"))  # Задержка при ошибке обработки очереди
    laravel_api_timeout_sec: float = float(os.getenv("LARAVEL_API_TIMEOUT_SEC", "10.0"))  # Таймаут для Laravel API
    node_offline_timeout_sec: int = int(os.getenv("NODE_OFFLINE_TIMEOUT_SEC", "120"))  # Таймаут офлайна по last_seen_at
    node_offline_check_interval_sec: int = int(os.getenv("NODE_OFFLINE_CHECK_INTERVAL_SEC", "30"))  # Интервал проверки офлайна
    
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))


def get_settings() -> Settings:
    """Получить настройки с проверкой обязательных параметров безопасности."""
    settings = Settings()
    
    # Проверка обязательных паролей в продакшене
    # Проверяем явно production, игнорируя пустые значения и dev/local окружения
    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""
    
    if is_prod:
        # В продакшене пароли обязательны
        if not settings.mqtt_pass:
            raise ValueError(
                "MQTT_PASS or MQTT_PASSWORD must be set in production environment"
            )
        if not settings.pg_pass:
            raise ValueError(
                "PG_PASS or POSTGRES_PASSWORD must be set in production environment"
            )
        if not settings.bridge_api_token:
            raise ValueError(
                "PY_API_TOKEN must be set in production environment for MQTT bridge security"
            )
        if not settings.history_logger_api_token:
            raise ValueError(
                "HISTORY_LOGGER_API_TOKEN or PY_API_TOKEN must be set in production environment for history-logger security"
            )
    
    return settings
