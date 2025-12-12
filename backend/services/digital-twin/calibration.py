"""
Модуль калибровки моделей Digital Twin по историческим данным.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.db import fetch

logger = logging.getLogger(__name__)


async def calibrate_ph_model(zone_id: int, days: int = 7) -> Dict[str, float]:
    """
    Калибровка модели pH по историческим данным.
    
    Анализирует:
    - Естественный дрифт pH (без коррекций)
    - Скорость коррекции после дозировок
    
    Returns:
        Словарь с параметрами: buffer_capacity, natural_drift, correction_rate
    """
    cutoff_date = utcnow() - timedelta(days=days)
    
    # Получаем историю pH (только валидные значения)
    ph_samples = await fetch(
        """
        SELECT ts, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND metric_type = 'PH'
          AND ts >= $2
          AND value IS NOT NULL
          AND value >= 0.0
          AND value <= 14.0
        ORDER BY ts ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    if not ph_samples or len(ph_samples) < 10:
        logger.warning(f"Zone {zone_id}: insufficient PH data for calibration, using defaults")
        return {
            "buffer_capacity": 0.1,
            "natural_drift": 0.01,
            "correction_rate": 0.05,
        }
    
    # Получаем команды дозирования кислоты/щелочи (только успешно выполненные)
    # Используем только команды со статусом DONE и result_code=0 для гарантии качества данных
    dosing_commands = await fetch(
        """
        SELECT created_at, params
        FROM commands
        WHERE zone_id = $1
          AND cmd IN ('run_pump', 'dose')
          AND channel IN ('pump_acid', 'pump_base', 'pump_ph_up', 'pump_ph_down')
          AND status = 'DONE'
          AND result_code = 0
          AND created_at IS NOT NULL
          AND created_at >= $2
        ORDER BY created_at ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    # Анализируем естественный дрифт (периоды без дозировок)
    natural_drifts = []
    last_dosing_time = None
    
    for sample in ph_samples:
        sample_time = sample["ts"]
        sample_value = float(sample["value"])
        
        # Проверяем, есть ли дозировка в ближайшие 2 часа после этого момента
        has_recent_dosing = False
        for cmd in dosing_commands:
            cmd_time = cmd["created_at"]
            if cmd_time > sample_time and (cmd_time - sample_time).total_seconds() < 7200:
                has_recent_dosing = True
                break
        
        if not has_recent_dosing and last_dosing_time is None:
            # Период без дозировок - анализируем дрифт
            if len(natural_drifts) > 0:
                prev_time, prev_value = natural_drifts[-1]
                time_diff_hours = (sample_time - prev_time).total_seconds() / 3600
                if time_diff_hours > 0:
                    drift_per_hour = (sample_value - prev_value) / time_diff_hours
                    natural_drifts.append((sample_time, sample_value, drift_per_hour))
            else:
                natural_drifts.append((sample_time, sample_value, None))
    
    # Вычисляем средний естественный дрифт
    drift_values = [d[2] for d in natural_drifts if d[2] is not None]
    if drift_values:
        natural_drift = abs(sum(drift_values) / len(drift_values))
        natural_drift = min(0.05, max(0.001, natural_drift))  # Ограничиваем разумными значениями
    else:
        natural_drift = 0.01  # Значение по умолчанию
    
    # Анализируем скорость коррекции после дозировок
    correction_rates = []
    for cmd in dosing_commands:
        cmd_time = cmd["created_at"]
        
        # Находим pH до и после дозировки
        ph_before = None
        ph_after = None
        
        for sample in ph_samples:
            sample_time = sample["ts"]
            if sample_time < cmd_time and (cmd_time - sample_time).total_seconds() < 3600:
                ph_before = float(sample["value"])
            elif sample_time > cmd_time and (sample_time - cmd_time).total_seconds() < 7200:
                ph_after = float(sample["value"])
                break
        
        if ph_before is not None and ph_after is not None:
            # Вычисляем изменение pH за час после дозировки
            time_diff_hours = 1.0  # Упрощение: считаем что прошёл час
            change = abs(ph_after - ph_before)
            if change > 0:
                correction_rate = change / time_diff_hours
                correction_rates.append(correction_rate)
    
    if correction_rates:
        correction_rate = sum(correction_rates) / len(correction_rates)
        correction_rate = min(0.2, max(0.01, correction_rate))  # Ограничиваем
    else:
        correction_rate = 0.05  # Значение по умолчанию
    
    return {
        "buffer_capacity": 0.1,  # Пока используем константу
        "natural_drift": round(natural_drift, 4),
        "correction_rate": round(correction_rate, 4),
    }


async def calibrate_ec_model(zone_id: int, days: int = 7) -> Dict[str, float]:
    """
    Калибровка модели EC по историческим данным.
    
    Анализирует:
    - Скорость испарения (увеличение EC)
    - Скорость добавления питательных веществ
    
    Returns:
        Словарь с параметрами: evaporation_rate, dilution_rate, nutrient_addition_rate
    """
    cutoff_date = utcnow() - timedelta(days=days)
    
    # Получаем историю EC (только валидные значения)
    ec_samples = await fetch(
        """
        SELECT ts, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND metric_type = 'EC'
          AND ts >= $2
          AND value IS NOT NULL
          AND value >= 0.0
          AND value <= 10.0
        ORDER BY ts ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    if not ec_samples or len(ec_samples) < 10:
        logger.warning(f"Zone {zone_id}: insufficient EC data for calibration, using defaults")
        return {
            "evaporation_rate": 0.02,
            "dilution_rate": 0.01,
            "nutrient_addition_rate": 0.03,
        }
    
    # Получаем команды дозирования питательных веществ (только успешно выполненные)
    # Используем только команды со статусом DONE и result_code=0 для гарантии качества данных
    nutrient_commands = await fetch(
        """
        SELECT created_at, params
        FROM commands
        WHERE zone_id = $1
          AND cmd IN ('run_pump', 'dose')
          AND channel IN ('pump_nutrient', 'pump_ec_up')
          AND status = 'DONE'
          AND result_code = 0
          AND created_at IS NOT NULL
          AND created_at >= $2
        ORDER BY created_at ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    # Анализируем испарение (увеличение EC без дозировок)
    evaporation_rates = []
    last_dosing_time = None
    
    for i in range(1, len(ec_samples)):
        prev_sample = ec_samples[i - 1]
        curr_sample = ec_samples[i]
        
        prev_time = prev_sample["ts"]
        curr_time = curr_sample["ts"]
        prev_value = float(prev_sample["value"])
        curr_value = float(curr_sample["value"])
        
        # Проверяем, была ли дозировка между этими точками
        has_dosing = False
        for cmd in nutrient_commands:
            cmd_time = cmd["created_at"]
            if prev_time < cmd_time < curr_time:
                has_dosing = True
                break
        
        if not has_dosing and curr_value > prev_value:
            # Увеличение EC без дозировок - это испарение
            time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
            if time_diff_hours > 0:
                increase = curr_value - prev_value
                rate = increase / (prev_value * time_diff_hours) if prev_value > 0 else 0
                if 0 < rate < 0.1:  # Разумные значения
                    evaporation_rates.append(rate)
    
    if evaporation_rates:
        evaporation_rate = sum(evaporation_rates) / len(evaporation_rates)
        evaporation_rate = min(0.05, max(0.001, evaporation_rate))
    else:
        evaporation_rate = 0.02  # Значение по умолчанию
    
    # Анализируем скорость добавления питательных веществ
    addition_rates = []
    for cmd in nutrient_commands:
        cmd_time = cmd["created_at"]
        
        # Находим EC до и после дозировки
        ec_before = None
        ec_after = None
        
        for sample in ec_samples:
            sample_time = sample["ts"]
            if sample_time < cmd_time and (cmd_time - sample_time).total_seconds() < 3600:
                ec_before = float(sample["value"])
            elif sample_time > cmd_time and (sample_time - cmd_time).total_seconds() < 7200:
                ec_after = float(sample["value"])
                break
        
        if ec_before is not None and ec_after is not None and ec_after > ec_before:
            time_diff_hours = 1.0
            change = ec_after - ec_before
            if ec_before > 0:
                rate = change / (ec_before * time_diff_hours)
                if 0 < rate < 0.2:
                    addition_rates.append(rate)
    
    if addition_rates:
        nutrient_addition_rate = sum(addition_rates) / len(addition_rates)
        nutrient_addition_rate = min(0.1, max(0.01, nutrient_addition_rate))
    else:
        nutrient_addition_rate = 0.03  # Значение по умолчанию
    
    return {
        "evaporation_rate": round(evaporation_rate, 4),
        "dilution_rate": 0.01,  # Пока используем константу
        "nutrient_addition_rate": round(nutrient_addition_rate, 4),
    }


async def calibrate_climate_model(zone_id: int, days: int = 7) -> Dict[str, float]:
    """
    Калибровка модели климата по историческим данным.
    
    Анализирует:
    - Потери тепла
    - Снижение влажности
    
    Returns:
        Словарь с параметрами: heat_loss_rate, humidity_decay_rate, ventilation_cooling
    """
    cutoff_date = utcnow() - timedelta(days=days)
    
    # Получаем историю температуры и влажности (только валидные значения)
    temp_samples = await fetch(
        """
        SELECT ts, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND metric_type = 'TEMP_AIR'
          AND ts >= $2
          AND value IS NOT NULL
          AND value >= -10.0
          AND value <= 50.0
        ORDER BY ts ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    humidity_samples = await fetch(
        """
        SELECT ts, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND metric_type = 'HUMIDITY'
          AND ts >= $2
          AND value IS NOT NULL
          AND value >= 0.0
          AND value <= 100.0
        ORDER BY ts ASC
        """,
        zone_id,
        cutoff_date,
    )
    
    if not temp_samples or len(temp_samples) < 10:
        logger.warning(f"Zone {zone_id}: insufficient climate data for calibration, using defaults")
        return {
            "heat_loss_rate": 0.5,
            "humidity_decay_rate": 0.02,
            "ventilation_cooling": 1.0,
        }
    
    # Анализируем потери тепла (снижение температуры без активного управления)
    heat_losses = []
    for i in range(1, len(temp_samples)):
        prev_sample = temp_samples[i - 1]
        curr_sample = temp_samples[i]
        
        prev_time = prev_sample["ts"]
        curr_time = curr_sample["ts"]
        prev_value = float(prev_sample["value"])
        curr_value = float(curr_sample["value"])
        
        if curr_value < prev_value:
            time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
            if time_diff_hours > 0:
                loss = (prev_value - curr_value) / time_diff_hours
                if 0 < loss < 2.0:  # Разумные значения
                    heat_losses.append(loss)
    
    if heat_losses:
        heat_loss_rate = sum(heat_losses) / len(heat_losses)
        heat_loss_rate = min(1.5, max(0.1, heat_loss_rate))
    else:
        heat_loss_rate = 0.5  # Значение по умолчанию
    
    # Анализируем снижение влажности
    humidity_decays = []
    if humidity_samples and len(humidity_samples) >= 2:
        for i in range(1, len(humidity_samples)):
            prev_sample = humidity_samples[i - 1]
            curr_sample = humidity_samples[i]
            
            prev_time = prev_sample["ts"]
            curr_time = curr_sample["ts"]
            prev_value = float(prev_sample["value"])
            curr_value = float(curr_sample["value"])
            
            if curr_value < prev_value:
                time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
                if time_diff_hours > 0 and prev_value > 0:
                    decay = (prev_value - curr_value) / (prev_value * time_diff_hours)
                    if 0 < decay < 0.1:
                        humidity_decays.append(decay)
    
    if humidity_decays:
        humidity_decay_rate = sum(humidity_decays) / len(humidity_decays)
        humidity_decay_rate = min(0.05, max(0.001, humidity_decay_rate))
    else:
        humidity_decay_rate = 0.02  # Значение по умолчанию
    
    return {
        "heat_loss_rate": round(heat_loss_rate, 4),
        "humidity_decay_rate": round(humidity_decay_rate, 4),
        "ventilation_cooling": 1.0,  # Пока используем константу
    }


async def calibrate_zone_models(zone_id: int, days: int = 7) -> Dict[str, Any]:
    """
    Полная калибровка всех моделей для зоны.
    
    Args:
        zone_id: ID зоны
        days: Количество дней исторических данных для анализа
    
    Returns:
        Словарь с калиброванными параметрами всех моделей
    """
    logger.info(f"Starting calibration for zone {zone_id} using last {days} days")
    
    ph_params = await calibrate_ph_model(zone_id, days)
    ec_params = await calibrate_ec_model(zone_id, days)
    climate_params = await calibrate_climate_model(zone_id, days)
    
    result = {
        "zone_id": zone_id,
        "calibrated_at": utcnow().isoformat(),
        "data_period_days": days,
        "models": {
            "ph": ph_params,
            "ec": ec_params,
            "climate": climate_params,
        },
    }
    
    logger.info(f"Calibration completed for zone {zone_id}")
    return result

