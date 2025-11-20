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
    # По умолчанию TLS включен для безопасности (можно отключить через MQTT_TLS=0)
    mqtt_tls: bool = os.getenv("MQTT_TLS", "1") == "1"
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

    telemetry_batch_size: int = int(os.getenv("TELEMETRY_BATCH_SIZE", "200"))
    telemetry_flush_ms: int = int(os.getenv("TELEMETRY_FLUSH_MS", "500"))
    command_timeout_sec: int = int(os.getenv("COMMAND_TIMEOUT_SEC", "30"))
    mqtt_zone_format: str = os.getenv("MQTT_ZONE_FORMAT", "id")  # id | uid
    service_port: int = int(os.getenv("SERVICE_PORT", "9300"))  # Порт для history-logger
    
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))


def get_settings() -> Settings:
    """Получить настройки с проверкой обязательных параметров безопасности."""
    settings = Settings()
    
    # Проверка обязательных паролей в продакшене
    is_prod = os.getenv("APP_ENV", "").lower() in ("production", "prod")
    
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
    
    return settings


