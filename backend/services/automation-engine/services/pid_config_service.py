"""
Сервис для чтения PID конфигов из БД.
Кеширует конфиги в памяти для быстрого доступа.
"""
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from common.utils.time import utcnow
from common.db import create_zone_event, execute, fetch
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


async def save_autotune_result(zone_id: int, correction_type: str, result: Dict[str, Any]) -> None:
    """
    Сохранить результат relay-autotune в zone_pid_configs и инвалидировать кеш.
    Обновляются только zone_coeffs.close/far (kp, ki), остальные поля конфига сохраняются.
    """
    pid_type = str(correction_type or "").strip().lower()
    if pid_type not in {"ph", "ec"}:
        raise ValueError(f"Unsupported PID type: {correction_type}")

    kp = float(result.get("kp") or 0.0)
    ki = float(result.get("ki") or 0.0)
    kd = float(result.get("kd") or 0.0)
    if kp <= 0:
        raise ValueError(f"Invalid autotune kp={kp}")
    if ki < 0:
        raise ValueError(f"Invalid autotune ki={ki}")

    rows = await fetch(
        """
        SELECT config
        FROM zone_pid_configs
        WHERE zone_id = $1 AND type = $2
        LIMIT 1
        """,
        zone_id,
        pid_type,
    )
    if rows:
        raw_config = rows[0].get("config")
        if isinstance(raw_config, dict):
            config_json = dict(raw_config)
        else:
            config_json = json.loads(raw_config)
    else:
        settings = get_settings()
        default_setpoint = 6.0 if pid_type == "ph" else 2.0
        config_json = _pid_config_to_json(_build_default_config(settings, default_setpoint, pid_type))

    zone_coeffs = config_json.get("zone_coeffs")
    if not isinstance(zone_coeffs, dict):
        zone_coeffs = {}
    close = zone_coeffs.get("close")
    if not isinstance(close, dict):
        close = {}
    far = zone_coeffs.get("far")
    if not isinstance(far, dict):
        far = {}

    close["kp"] = kp
    close["ki"] = ki
    close["kd"] = float(close.get("kd", kd) or 0.0)
    far["kp"] = kp
    far["ki"] = ki
    far["kd"] = float(far.get("kd", kd) or 0.0)
    zone_coeffs["close"] = close
    zone_coeffs["far"] = far
    config_json["zone_coeffs"] = zone_coeffs

    config_json["autotune_meta"] = {
        "source": result.get("source") or "relay_autotune",
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "ku": float(result.get("ku") or 0.0),
        "tu_sec": float(result.get("tu_sec") or 0.0),
        "oscillation_amplitude": float(result.get("oscillation_amplitude") or 0.0),
        "cycles_detected": int(result.get("cycles_detected") or 0),
        "duration_sec": float(result.get("duration_sec") or 0.0),
        "tuned_at": result.get("tuned_at"),
    }
    # Backward compatibility: убираем legacy-ключ после миграции на autotune_meta.
    config_json.pop("autotune", None)

    await execute(
        """
        INSERT INTO zone_pid_configs (zone_id, type, config, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (zone_id, type) DO UPDATE
        SET config = EXCLUDED.config,
            updated_at = NOW()
        """,
        zone_id,
        pid_type,
        config_json,
    )

    invalidate_cache(zone_id, pid_type)
    await create_zone_event(
        zone_id,
        "PID_CONFIG_UPDATED",
        {
            "type": pid_type,
            "source": "relay_autotune",
            "new_config": {
                "zone_coeffs": {
                    "close": {"kp": close["kp"], "ki": close["ki"], "kd": close["kd"]},
                    "far": {"kp": far["kp"], "ki": far["ki"], "kd": far["kd"]},
                }
            },
            "autotune_meta": config_json.get("autotune_meta"),
        },
    )
    await create_zone_event(
        zone_id,
        "RELAY_AUTOTUNE_COMPLETED",
        {
            "type": pid_type,
            "source": "relay_autotune",
            "kp": kp,
            "ki": ki,
            "kd": kd,
            "ku": float(result.get("ku") or 0.0),
            "tu_sec": float(result.get("tu_sec") or 0.0),
            "oscillation_amplitude": float(result.get("oscillation_amplitude") or 0.0),
            "cycles_detected": int(result.get("cycles_detected") or 0),
            "duration_sec": float(result.get("duration_sec") or 0.0),
            "tuned_at": result.get("tuned_at"),
        },
    )
    logger.info(
        "Saved relay autotune PID config: zone=%s type=%s kp=%.4f ki=%.5f",
        zone_id,
        pid_type,
        kp,
        ki,
    )


def _json_to_pid_config(config_json: Dict[str, Any], setpoint: float, correction_type: str) -> AdaptivePidConfig:
    """Преобразовать JSON конфиг в AdaptivePidConfig."""
    settings = get_settings()
    # Backward compatibility: старый ключ `autotune` -> новый `autotune_meta`.
    autotune_meta = config_json.get("autotune_meta")
    if not isinstance(autotune_meta, dict):
        legacy_autotune = config_json.get("autotune")
        if isinstance(legacy_autotune, dict):
            autotune_meta = legacy_autotune
            config_json["autotune_meta"] = legacy_autotune

    def _parse_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    if correction_type == "ph":
        default_close_coeffs = PidZoneCoeffs(settings.PH_PID_KP_CLOSE, settings.PH_PID_KI_CLOSE, settings.PH_PID_KD_CLOSE)
        default_far_coeffs = PidZoneCoeffs(settings.PH_PID_KP_FAR, settings.PH_PID_KI_FAR, settings.PH_PID_KD_FAR)
        default_dead_zone = settings.PH_PID_DEAD_ZONE
        default_close_zone = settings.PH_PID_CLOSE_ZONE
        default_far_zone = settings.PH_PID_FAR_ZONE
        default_max_output = settings.PH_PID_MAX_OUTPUT
        default_max_integral = settings.PH_PID_MAX_INTEGRAL
        default_min_interval_ms = settings.PH_PID_MIN_INTERVAL_MS
        default_derivative_filter_alpha = settings.PH_PID_DERIVATIVE_FILTER_ALPHA
    else:
        default_close_coeffs = PidZoneCoeffs(settings.EC_PID_KP_CLOSE, settings.EC_PID_KI_CLOSE, settings.EC_PID_KD_CLOSE)
        default_far_coeffs = PidZoneCoeffs(settings.EC_PID_KP_FAR, settings.EC_PID_KI_FAR, settings.EC_PID_KD_FAR)
        default_dead_zone = settings.EC_PID_DEAD_ZONE
        default_close_zone = settings.EC_PID_CLOSE_ZONE
        default_far_zone = settings.EC_PID_FAR_ZONE
        default_max_output = settings.EC_PID_MAX_OUTPUT
        default_max_integral = settings.EC_PID_MAX_INTEGRAL
        default_min_interval_ms = settings.EC_PID_MIN_INTERVAL_MS
        default_derivative_filter_alpha = settings.EC_PID_DERIVATIVE_FILTER_ALPHA

    coeffs = config_json.get("zone_coeffs")
    if not isinstance(coeffs, dict):
        logger.warning("Invalid zone_coeffs type: %s, expected dict. Using defaults.", type(coeffs))
        coeffs = {}

    close_cfg = coeffs.get("close")
    if isinstance(close_cfg, dict):
        close_ki = _parse_float(close_cfg.get("ki"), default_close_coeffs.ki)
        if close_ki <= 0:
            close_ki = float(default_close_coeffs.ki)
        close_coeffs = PidZoneCoeffs(
            kp=_parse_float(close_cfg.get("kp"), default_close_coeffs.kp),
            ki=close_ki,
            kd=_parse_float(close_cfg.get("kd"), default_close_coeffs.kd),
        )
    else:
        logger.warning("Missing or invalid 'close' zone_coeffs. Using defaults.")
        close_coeffs = default_close_coeffs

    far_cfg = coeffs.get("far")
    if isinstance(far_cfg, dict):
        far_ki = _parse_float(far_cfg.get("ki"), default_far_coeffs.ki)
        if far_ki <= 0:
            far_ki = float(default_far_coeffs.ki)
        far_coeffs = PidZoneCoeffs(
            kp=_parse_float(far_cfg.get("kp"), default_far_coeffs.kp),
            ki=far_ki,
            kd=_parse_float(far_cfg.get("kd"), default_far_coeffs.kd),
        )
    else:
        logger.warning("Missing or invalid 'far' zone_coeffs. Using defaults.")
        far_coeffs = default_far_coeffs

    zone_coeffs = {
        PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
        PidZone.CLOSE: close_coeffs,
        PidZone.FAR: far_coeffs,
    }

    pid_config = AdaptivePidConfig(
        setpoint=setpoint,  # Используем setpoint из рецепта, а не из конфига
        dead_zone=float(config_json.get('dead_zone', default_dead_zone)),
        close_zone=float(config_json.get('close_zone', default_close_zone)),
        far_zone=float(config_json.get('far_zone', default_far_zone)),
        zone_coeffs=zone_coeffs,
        max_output=float(config_json.get('max_output', default_max_output)),
        min_output=float(config_json.get('min_output', 0.0)),
        max_integral=float(config_json.get('max_integral', default_max_integral)),
        anti_windup_mode=str(config_json.get('anti_windup_mode', settings.PID_ANTI_WINDUP_MODE)),
        back_calculation_gain=float(config_json.get('back_calculation_gain', settings.PID_BACK_CALCULATION_GAIN)),
        derivative_filter_alpha=float(config_json.get('derivative_filter_alpha', default_derivative_filter_alpha)),
        min_interval_ms=int(config_json.get('min_interval_ms', default_min_interval_ms)),
    )
    if isinstance(autotune_meta, dict):
        setattr(pid_config, "autotune_meta", autotune_meta)
    return pid_config


def _pid_config_to_json(config: AdaptivePidConfig) -> Dict[str, Any]:
    close = config.zone_coeffs.get(PidZone.CLOSE, PidZoneCoeffs(0.0, 0.0, 0.0))
    far = config.zone_coeffs.get(PidZone.FAR, PidZoneCoeffs(0.0, 0.0, 0.0))
    result: Dict[str, Any] = {
        "target": float(config.setpoint),
        "dead_zone": float(config.dead_zone),
        "close_zone": float(config.close_zone),
        "far_zone": float(config.far_zone),
        "zone_coeffs": {
            "close": {
                "kp": float(close.kp),
                "ki": float(close.ki),
                "kd": float(close.kd),
            },
            "far": {
                "kp": float(far.kp),
                "ki": float(far.ki),
                "kd": float(far.kd),
            },
        },
        "max_output": float(config.max_output),
        "min_output": float(config.min_output),
        "max_integral": float(config.max_integral),
        "anti_windup_mode": str(config.anti_windup_mode),
        "back_calculation_gain": float(config.back_calculation_gain),
        "derivative_filter_alpha": float(config.derivative_filter_alpha),
        "min_interval_ms": int(config.min_interval_ms),
    }
    autotune_meta = getattr(config, "autotune_meta", None)
    if isinstance(autotune_meta, dict):
        result["autotune_meta"] = autotune_meta
    return result


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
            max_integral=settings.PH_PID_MAX_INTEGRAL,
            anti_windup_mode=settings.PID_ANTI_WINDUP_MODE,
            back_calculation_gain=settings.PID_BACK_CALCULATION_GAIN,
            derivative_filter_alpha=settings.PH_PID_DERIVATIVE_FILTER_ALPHA,
            min_interval_ms=settings.PH_PID_MIN_INTERVAL_MS,
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
            max_integral=settings.EC_PID_MAX_INTEGRAL,
            anti_windup_mode=settings.PID_ANTI_WINDUP_MODE,
            back_calculation_gain=settings.PID_BACK_CALCULATION_GAIN,
            derivative_filter_alpha=settings.EC_PID_DERIVATIVE_FILTER_ALPHA,
            min_interval_ms=settings.EC_PID_MIN_INTERVAL_MS,
        )
