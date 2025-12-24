"""
Сервис для чтения PID конфигов из БД.
Кеширует конфиги в памяти для быстрого доступа.
"""
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from common.utils.time import utcnow
from common.db import fetch
from config.settings import get_settings
from utils.adaptive_pid import AdaptivePidConfig, PidZone, PidZoneCoeffs

logger = logging.getLogger(__name__)

# Кеш конфигов: {zone_id: {type: (config, timestamp, db_updated_at)}}
_config_cache: Dict[int, Dict[str, Tuple[AdaptivePidConfig, datetime, Optional[datetime]]]] = {}
_cache_ttl_seconds = 15  # TTL кеша: 15 секунд (уменьшено для уменьшения race condition)


async def get_config(zone_id: int, correction_type: str, setpoint: float) -> Optional[AdaptivePidConfig]:
    """
    Получить PID конфиг для зоны и типа.
    
    Args:
        zone_id: ID зоны
        correction_type: Тип корректировки ('ph' или 'ec')
        setpoint: Целевое значение (из рецепта)
    
    Returns:
        AdaptivePidConfig или None (если конфиг не найден и дефолты не используются)
    """
    # Проверяем кеш
    cache_key = (zone_id, correction_type)
    if zone_id in _config_cache and correction_type in _config_cache[zone_id]:
        config, timestamp, cached_db_updated_at = _config_cache[zone_id][correction_type]
        age = utcnow() - timestamp
        
        if age.total_seconds() < _cache_ttl_seconds:
            # Проверяем, не обновился ли конфиг в БД
            try:
                rows = await fetch(
                    """
                    SELECT updated_at
                    FROM zone_pid_configs
                    WHERE zone_id = $1 AND type = $2
                    """,
                    zone_id, correction_type
                )
                
                if rows:
                    db_updated_at = rows[0]['updated_at']
                    # Преобразуем в datetime если нужно и приводим к aware UTC
                    if isinstance(db_updated_at, str):
                        db_updated_at = datetime.fromisoformat(db_updated_at.replace('Z', '+00:00'))
                    if db_updated_at.tzinfo is None:
                        db_updated_at = db_updated_at.replace(tzinfo=timezone.utc)
                    elif db_updated_at.tzinfo != timezone.utc:
                        db_updated_at = db_updated_at.astimezone(timezone.utc)
                    
                    # Приводим cached_db_updated_at к aware UTC для корректного сравнения
                    if cached_db_updated_at is not None:
                        if cached_db_updated_at.tzinfo is None:
                            cached_db_updated_at = cached_db_updated_at.replace(tzinfo=timezone.utc)
                        elif cached_db_updated_at.tzinfo != timezone.utc:
                            cached_db_updated_at = cached_db_updated_at.astimezone(timezone.utc)
                    
                    # Если конфиг обновился в БД, инвалидируем кеш
                    if cached_db_updated_at is None or db_updated_at > cached_db_updated_at:
                        # Конфиг обновился - инвалидируем кеш и перезагружаем
                        _config_cache[zone_id].pop(correction_type, None)
                        logger.debug(f"PID config cache invalidated: zone={zone_id}, type={correction_type} (updated in DB)")
                        # Продолжаем загрузку из БД ниже
                    else:
                        # Конфиг не обновился - используем кеш
                        # Обновляем cached_db_updated_at в кеше
                        _config_cache[zone_id][correction_type] = (config, timestamp, db_updated_at)
                        config.setpoint = setpoint
                        return config
                else:
                    # Конфиг удален из БД - если это был дефолтный конфиг (cached_db_updated_at == None), используем кеш
                    if cached_db_updated_at is None:
                        # Это был дефолтный конфиг, конфига в БД нет - используем кеш
                        config.setpoint = setpoint
                        return config
                    else:
                        # Конфиг был в БД, но теперь удален - инвалидируем кеш
                        _config_cache[zone_id].pop(correction_type, None)
                        logger.debug(f"PID config cache invalidated: zone={zone_id}, type={correction_type} (deleted from DB)")
                        # Продолжаем загрузку дефолтов ниже
            except Exception as e:
                # В случае ошибки проверки БД, используем кеш если он не слишком старый
                logger.warning(f"Failed to check PID config update time: {e}. Using cached config.")
                config.setpoint = setpoint
                return config
    
    # Читаем из БД
    try:
        rows = await fetch(
            """
            SELECT config, updated_at
            FROM zone_pid_configs
            WHERE zone_id = $1 AND type = $2
            """,
            zone_id, correction_type
        )
        
        if rows:
            # Конфиг найден в БД
            row = rows[0]
            # asyncpg возвращает JSONB как dict
            config_json = row['config'] if isinstance(row['config'], dict) else json.loads(row['config'])
            db_updated_at = row['updated_at']
            # Преобразуем в datetime если нужно и приводим к aware UTC
            if isinstance(db_updated_at, str):
                db_updated_at = datetime.fromisoformat(db_updated_at.replace('Z', '+00:00'))
            if db_updated_at.tzinfo is None:
                db_updated_at = db_updated_at.replace(tzinfo=timezone.utc)
            elif db_updated_at.tzinfo != timezone.utc:
                db_updated_at = db_updated_at.astimezone(timezone.utc)
            
            # Преобразуем JSONB в AdaptivePidConfig
            pid_config = _json_to_pid_config(config_json, setpoint, correction_type)
            
            # Сохраняем в кеш с timestamp обновления из БД
            if zone_id not in _config_cache:
                _config_cache[zone_id] = {}
            _config_cache[zone_id][correction_type] = (pid_config, utcnow(), db_updated_at)
            
            logger.debug(f"Loaded PID config from DB: zone={zone_id}, type={correction_type}")
            return pid_config
        else:
            # Конфиг не найден - используем дефолты
            settings = get_settings()
            pid_config = _build_default_config(settings, setpoint, correction_type)
            
            # Сохраняем дефолтный конфиг в кеш (без db_updated_at, так как конфига нет в БД)
            if zone_id not in _config_cache:
                _config_cache[zone_id] = {}
            _config_cache[zone_id][correction_type] = (pid_config, utcnow(), None)
            
            logger.info(f"Using default PID config: zone={zone_id}, type={correction_type}")
            return pid_config
            
    except Exception as e:
        logger.error(f"Failed to load PID config from DB: {e}", exc_info=True)
        # В случае ошибки используем дефолты
        settings = get_settings()
        return _build_default_config(settings, setpoint, correction_type)


def invalidate_cache(zone_id: int, correction_type: Optional[str] = None):
    """
    Инвалидировать кеш конфига для зоны.
    
    Args:
        zone_id: ID зоны
        correction_type: Тип корректировки (опционально, если None - инвалидирует все типы)
    """
    if zone_id in _config_cache:
        if correction_type:
            _config_cache[zone_id].pop(correction_type, None)
        else:
            _config_cache[zone_id].clear()
        logger.debug(f"Invalidated PID config cache: zone={zone_id}, type={correction_type or 'all'}")


def _json_to_pid_config(config_json: Dict[str, Any], setpoint: float, correction_type: str) -> AdaptivePidConfig:
    """Преобразовать JSON конфиг в AdaptivePidConfig."""
    zone_coeffs = {}
    
    # Коэффициенты для зон
    if 'zone_coeffs' in config_json:
        coeffs = config_json['zone_coeffs']
        if not isinstance(coeffs, dict):
            logger.warning(f"Invalid zone_coeffs type: {type(coeffs)}, expected dict. Using defaults.")
            coeffs = {}
        
        if 'close' in coeffs and isinstance(coeffs['close'], dict):
            zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
                kp=float(coeffs['close'].get('kp', 0.0)),
                ki=float(coeffs['close'].get('ki', 0.0)),
                kd=float(coeffs['close'].get('kd', 0.0)),
            )
        else:
            logger.warning(f"Missing or invalid 'close' zone_coeffs. Using defaults.")
            # Используем дефолтные значения для close зоны
            settings = get_settings()
            if correction_type == 'ph':
                zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
                    settings.PH_PID_KP_CLOSE,
                    settings.PH_PID_KI_CLOSE,
                    settings.PH_PID_KD_CLOSE,
                )
            else:
                zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
                    settings.EC_PID_KP_CLOSE,
                    settings.EC_PID_KI_CLOSE,
                    settings.EC_PID_KD_CLOSE,
                )
        
        if 'far' in coeffs and isinstance(coeffs['far'], dict):
            zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
                kp=float(coeffs['far'].get('kp', 0.0)),
                ki=float(coeffs['far'].get('ki', 0.0)),
                kd=float(coeffs['far'].get('kd', 0.0)),
            )
        else:
            logger.warning(f"Missing or invalid 'far' zone_coeffs. Using defaults.")
            # Используем дефолтные значения для far зоны
            settings = get_settings()
            if correction_type == 'ph':
                zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
                    settings.PH_PID_KP_FAR,
                    settings.PH_PID_KI_FAR,
                    settings.PH_PID_KD_FAR,
                )
            else:
                zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
                    settings.EC_PID_KP_FAR,
                    settings.EC_PID_KI_FAR,
                    settings.EC_PID_KD_FAR,
                )
    
    # Если zone_coeffs отсутствует или пустой, используем дефолтные значения
    if not zone_coeffs or PidZone.CLOSE not in zone_coeffs or PidZone.FAR not in zone_coeffs:
        settings = get_settings()
        if correction_type == 'ph':
            if PidZone.CLOSE not in zone_coeffs:
                zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
                    settings.PH_PID_KP_CLOSE,
                    settings.PH_PID_KI_CLOSE,
                    settings.PH_PID_KD_CLOSE,
                )
            if PidZone.FAR not in zone_coeffs:
                zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
                    settings.PH_PID_KP_FAR,
                    settings.PH_PID_KI_FAR,
                    settings.PH_PID_KD_FAR,
                )
        else:  # ec
            if PidZone.CLOSE not in zone_coeffs:
                zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
                    settings.EC_PID_KP_CLOSE,
                    settings.EC_PID_KI_CLOSE,
                    settings.EC_PID_KD_CLOSE,
                )
            if PidZone.FAR not in zone_coeffs:
                zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
                    settings.EC_PID_KP_FAR,
                    settings.EC_PID_KI_FAR,
                    settings.EC_PID_KD_FAR,
                )
    
    # Dead zone всегда имеет нулевые коэффициенты
    zone_coeffs[PidZone.DEAD] = PidZoneCoeffs(0.0, 0.0, 0.0)
    
    return AdaptivePidConfig(
        setpoint=setpoint,  # Используем setpoint из рецепта, а не из конфига
        dead_zone=float(config_json.get('dead_zone', 0.2)),
        close_zone=float(config_json.get('close_zone', 0.5)),
        far_zone=float(config_json.get('far_zone', 1.0)),
        zone_coeffs=zone_coeffs,
        max_output=float(config_json.get('max_output', 50.0)),
        min_output=0.0,
        max_integral=100.0,
        min_interval_ms=int(config_json.get('min_interval_ms', 60000)),
        enable_autotune=bool(config_json.get('enable_autotune', False)),
        adaptation_rate=float(config_json.get('adaptation_rate', 0.05)),
    )


def _build_default_config(settings, setpoint: float, correction_type: str) -> AdaptivePidConfig:
    """Построить дефолтный конфиг из AutomationSettings."""
    if correction_type == 'ph':
        return AdaptivePidConfig(
            setpoint=setpoint,
            dead_zone=settings.PH_PID_DEAD_ZONE,
            close_zone=settings.PH_PID_CLOSE_ZONE,
            far_zone=settings.PH_PID_FAR_ZONE,
            zone_coeffs={
                PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                PidZone.CLOSE: PidZoneCoeffs(
                    settings.PH_PID_KP_CLOSE,
                    settings.PH_PID_KI_CLOSE,
                    settings.PH_PID_KD_CLOSE,
                ),
                PidZone.FAR: PidZoneCoeffs(
                    settings.PH_PID_KP_FAR,
                    settings.PH_PID_KI_FAR,
                    settings.PH_PID_KD_FAR,
                ),
            },
            max_output=settings.PH_PID_MAX_OUTPUT,
            min_output=0.0,
            max_integral=100.0,
            min_interval_ms=settings.PH_PID_MIN_INTERVAL_MS,
            enable_autotune=settings.PH_PID_ENABLE_AUTOTUNE,
            adaptation_rate=settings.PH_PID_ADAPTATION_RATE,
        )
    else:  # ec
        return AdaptivePidConfig(
            setpoint=setpoint,
            dead_zone=settings.EC_PID_DEAD_ZONE,
            close_zone=settings.EC_PID_CLOSE_ZONE,
            far_zone=settings.EC_PID_FAR_ZONE,
            zone_coeffs={
                PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                PidZone.CLOSE: PidZoneCoeffs(
                    settings.EC_PID_KP_CLOSE,
                    settings.EC_PID_KI_CLOSE,
                    settings.EC_PID_KD_CLOSE,
                ),
                PidZone.FAR: PidZoneCoeffs(
                    settings.EC_PID_KP_FAR,
                    settings.EC_PID_KI_FAR,
                    settings.EC_PID_KD_FAR,
                ),
            },
            max_output=settings.EC_PID_MAX_OUTPUT,
            min_output=0.0,
            max_integral=100.0,
            min_interval_ms=settings.EC_PID_MIN_INTERVAL_MS,
            enable_autotune=settings.EC_PID_ENABLE_AUTOTUNE,
            adaptation_rate=settings.EC_PID_ADAPTATION_RATE,
        )

