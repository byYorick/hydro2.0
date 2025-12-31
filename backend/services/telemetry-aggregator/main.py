"""
Telemetry Aggregator - агрегация телеметрии.
Периодически агрегирует telemetry_samples в telemetry_agg_1m, telemetry_agg_1h, telemetry_daily.
Согласно BACKEND_REFACTOR_PLAN.md раздел 17.
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.env import get_settings
from common.db import fetch, execute
from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)

AGGREGATION_RUNS = Counter("aggregation_runs_total", "Aggregation runs", ["type"])
AGGREGATION_RECORDS = Counter("aggregation_records_total", "Aggregated records", ["type"])
AGGREGATION_LAT = Histogram("aggregation_seconds", "Aggregation duration seconds", ["type"])
AGGREGATION_ERRORS = Counter("aggregation_errors_total", "Aggregation errors", ["type"])
CLEANUP_RUNS = Counter("cleanup_runs_total", "Cleanup runs")
CLEANUP_DELETED = Counter("cleanup_deleted_total", "Deleted records", ["table"])
CLEANUP_LAT = Histogram("cleanup_seconds", "Cleanup duration seconds")

# Error backoff state
_error_count = 0
_last_error_time: Optional[datetime] = None
_backoff_until: Optional[datetime] = None


async def get_last_ts(aggregation_type: str) -> Optional[datetime]:
    """
    Получить последнюю обработанную временную метку для типа агрегации.
    
    Args:
        aggregation_type: '1m', '1h', или 'daily'
    
    Returns:
        datetime последней обработки или None
    """
    rows = await fetch(
        """
        SELECT last_ts
        FROM aggregator_state
        WHERE aggregation_type = $1
        """,
        aggregation_type,
    )
    
    if rows and rows[0].get("last_ts"):
        return rows[0]["last_ts"]
    
    # Если нет записи, возвращаем None (начнём с начала данных)
    return None


async def update_last_ts(aggregation_type: str, last_ts: datetime) -> None:
    """
    Обновить последнюю обработанную временную метку.
    
    Args:
        aggregation_type: '1m', '1h', или 'daily'
        last_ts: Временная метка последней обработки
    """
    await execute(
        """
        UPDATE aggregator_state
        SET last_ts = $1, updated_at = NOW()
        WHERE aggregation_type = $2
        """,
        last_ts,
        aggregation_type,
    )


async def _check_error_backoff() -> bool:
    """
    Проверить, нужно ли применять backoff из-за серии ошибок.
    
    Returns:
        True если нужно применить backoff, False если можно продолжать
    """
    global _error_count, _last_error_time, _backoff_until
    
    now = utcnow()
    
    # Если есть активный backoff, проверяем, не истек ли он
    if _backoff_until and now < _backoff_until:
        remaining = (_backoff_until - now).total_seconds()
        logger.warning(
            f"Error backoff active: skipping aggregation, {remaining:.1f}s remaining",
            extra={
                'backoff_until': _backoff_until.isoformat(),
                'error_count': _error_count
            }
        )
        return True
    
    # Если backoff истек, сбрасываем счетчик
    if _backoff_until and now >= _backoff_until:
        logger.info(
            f"Error backoff expired, resetting error count",
            extra={'previous_error_count': _error_count}
        )
        _error_count = 0
        _backoff_until = None
    
    return False


async def _record_error() -> None:
    """
    Записать ошибку и применить backoff при серии исключений.
    """
    global _error_count, _last_error_time, _backoff_until
    
    _error_count += 1
    _last_error_time = utcnow()
    
    # Применяем exponential backoff при серии ошибок
    # Пороги: 3 ошибки -> 30s, 5 ошибок -> 2min, 10 ошибок -> 10min
    if _error_count >= 10:
        backoff_seconds = 600  # 10 минут
    elif _error_count >= 5:
        backoff_seconds = 120  # 2 минуты
    elif _error_count >= 3:
        backoff_seconds = 30  # 30 секунд
    else:
        backoff_seconds = 0
    
    if backoff_seconds > 0:
        _backoff_until = utcnow() + timedelta(seconds=backoff_seconds)
        logger.error(
            f"Error backoff activated: {_error_count} consecutive errors, "
            f"backing off for {backoff_seconds}s to reduce infrastructure pressure",
            extra={
                'error_count': _error_count,
                'backoff_seconds': backoff_seconds,
                'backoff_until': _backoff_until.isoformat()
            }
        )


async def _record_success() -> None:
    """Сбросить счетчик ошибок при успешной операции."""
    global _error_count, _backoff_until
    
    if _error_count > 0:
        logger.info(
            f"Aggregation succeeded, resetting error count (was {_error_count})",
            extra={'previous_error_count': _error_count}
        )
        _error_count = 0
        _backoff_until = None


async def aggregate_1m() -> int:
    """
    Агрегировать телеметрию по 1 минуте.
    
    Returns:
        Количество созданных записей
    """
    # Проверяем error backoff перед началом агрегации
    if await _check_error_backoff():
        return 0
    
    with AGGREGATION_LAT.labels(type="1m").time():
        try:
            last_ts = await get_last_ts("1m")
            
            # Если нет последней метки, берём последний час
            if last_ts is None:
                last_ts = utcnow() - timedelta(hours=1)
            
            # Агрегируем данные из telemetry_samples
            # Пробуем использовать time_bucket (TimescaleDB), если не работает - используем date_trunc
            try:
                rows = await fetch(
                    """
                    INSERT INTO telemetry_agg_1m (
                        zone_id, node_id, channel, metric_type,
                        value_avg, value_min, value_max, value_median, sample_count, ts
                    )
                    SELECT 
                        ts.zone_id,
                        s.node_id,
                        ts.metadata->>'channel' as channel,
                        s.type::text as metric_type,
                        AVG(ts.value)::float as value_avg,
                        MIN(ts.value)::float as value_min,
                        MAX(ts.value)::float as value_max,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ts.value)::float as value_median,
                        COUNT(*)::int as sample_count,
                        time_bucket('1 minute', ts.ts) as ts
                    FROM telemetry_samples ts
                    LEFT JOIN sensors s ON s.id = ts.sensor_id
                    WHERE ts.ts > $1 AND ts.ts <= NOW()
                    GROUP BY
                        ts.zone_id,
                        s.node_id,
                        ts.metadata->>'channel',
                        s.type::text,
                        time_bucket('1 minute', ts.ts)
                    ON CONFLICT (zone_id, node_id, channel, metric_type, ts) 
                    DO UPDATE SET
                        value_avg = EXCLUDED.value_avg,
                        value_min = EXCLUDED.value_min,
                        value_max = EXCLUDED.value_max,
                        value_median = EXCLUDED.value_median,
                        sample_count = EXCLUDED.sample_count
                    RETURNING ts
                    """,
                    last_ts,
                )
            except Exception:
                # Если time_bucket не доступен, используем date_trunc
                rows = await fetch(
                    """
                    INSERT INTO telemetry_agg_1m (
                        zone_id, node_id, channel, metric_type,
                        value_avg, value_min, value_max, value_median, sample_count, ts
                    )
                    SELECT 
                        ts.zone_id,
                        s.node_id,
                        ts.metadata->>'channel' as channel,
                        s.type::text as metric_type,
                        AVG(ts.value)::float as value_avg,
                        MIN(ts.value)::float as value_min,
                        MAX(ts.value)::float as value_max,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ts.value)::float as value_median,
                        COUNT(*)::int as sample_count,
                        date_trunc('minute', ts.ts) as ts
                    FROM telemetry_samples ts
                    LEFT JOIN sensors s ON s.id = ts.sensor_id
                    WHERE ts.ts > $1 AND ts.ts <= NOW()
                    GROUP BY
                        ts.zone_id,
                        s.node_id,
                        ts.metadata->>'channel',
                        s.type::text,
                        date_trunc('minute', ts.ts)
                    ON CONFLICT (zone_id, node_id, channel, metric_type, ts) 
                    DO UPDATE SET
                        value_avg = EXCLUDED.value_avg,
                        value_min = EXCLUDED.value_min,
                        value_max = EXCLUDED.value_max,
                        value_median = EXCLUDED.value_median,
                        sample_count = EXCLUDED.sample_count
                    RETURNING ts
                    """,
                    last_ts,
                )
            
            count = len(rows) if rows else 0
            
            # Обновляем last_ts
            if count > 0:
                # Берём максимальную временную метку
                max_ts = max(row["ts"] for row in rows)
                await update_last_ts("1m", max_ts)
            
            AGGREGATION_RECORDS.labels(type="1m").inc(count)
            logger.info(f"Aggregated 1m: {count} records")
            
            # Сбрасываем счетчик ошибок при успехе
            await _record_success()
            
            return count
        except Exception as e:
            AGGREGATION_ERRORS.labels(type="1m").inc()
            await _record_error()
            logger.error(
                f"Error aggregating 1m: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'consecutive_errors': _error_count
                }
            )
            return 0


async def aggregate_1h() -> int:
    """
    Агрегировать телеметрию по 1 часу из telemetry_agg_1m.
    
    Returns:
        Количество созданных записей
    """
    # Проверяем error backoff перед началом агрегации
    if await _check_error_backoff():
        return 0
    
    with AGGREGATION_LAT.labels(type="1h").time():
        try:
            last_ts = await get_last_ts("1h")
            
            # Если нет последней метки, берём последние 24 часа
            if last_ts is None:
                last_ts = utcnow() - timedelta(hours=24)
            
            # Агрегируем данные из telemetry_agg_1m
            try:
                rows = await fetch(
                    """
                    INSERT INTO telemetry_agg_1h (
                        zone_id, node_id, channel, metric_type,
                        value_avg, value_min, value_max, value_median, sample_count, ts
                    )
                    SELECT 
                        zone_id,
                        node_id,
                        channel,
                        metric_type,
                        AVG(value_avg)::float as value_avg,
                        MIN(value_min)::float as value_min,
                        MAX(value_max)::float as value_max,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_avg)::float as value_median,
                        SUM(sample_count)::int as sample_count,
                        time_bucket('1 hour', ts) as ts
                    FROM telemetry_agg_1m
                    WHERE ts > $1 AND ts <= NOW()
                    GROUP BY zone_id, node_id, channel, metric_type, time_bucket('1 hour', ts)
                    ON CONFLICT (zone_id, node_id, channel, metric_type, ts) 
                    DO UPDATE SET
                        value_avg = EXCLUDED.value_avg,
                        value_min = EXCLUDED.value_min,
                        value_max = EXCLUDED.value_max,
                        value_median = EXCLUDED.value_median,
                        sample_count = EXCLUDED.sample_count
                    RETURNING ts
                    """,
                    last_ts,
                )
            except Exception:
                # Если time_bucket не доступен, используем date_trunc
                rows = await fetch(
                    """
                    INSERT INTO telemetry_agg_1h (
                        zone_id, node_id, channel, metric_type,
                        value_avg, value_min, value_max, value_median, sample_count, ts
                    )
                    SELECT 
                        zone_id,
                        node_id,
                        channel,
                        metric_type,
                        AVG(value_avg)::float as value_avg,
                        MIN(value_min)::float as value_min,
                        MAX(value_max)::float as value_max,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_avg)::float as value_median,
                        SUM(sample_count)::int as sample_count,
                        date_trunc('hour', ts) as ts
                    FROM telemetry_agg_1m
                    WHERE ts > $1 AND ts <= NOW()
                    GROUP BY zone_id, node_id, channel, metric_type, date_trunc('hour', ts)
                    ON CONFLICT (zone_id, node_id, channel, metric_type, ts) 
                    DO UPDATE SET
                        value_avg = EXCLUDED.value_avg,
                        value_min = EXCLUDED.value_min,
                        value_max = EXCLUDED.value_max,
                        value_median = EXCLUDED.value_median,
                        sample_count = EXCLUDED.sample_count
                    RETURNING ts
                    """,
                    last_ts,
                )
            
            count = len(rows) if rows else 0
            
            # Обновляем last_ts
            if count > 0:
                max_ts = max(row["ts"] for row in rows)
                await update_last_ts("1h", max_ts)
            
            AGGREGATION_RECORDS.labels(type="1h").inc(count)
            logger.info(f"Aggregated 1h: {count} records")
            
            # Сбрасываем счетчик ошибок при успехе
            await _record_success()
            
            return count
        except Exception as e:
            AGGREGATION_ERRORS.labels(type="1h").inc()
            await _record_error()
            logger.error(
                f"Error aggregating 1h: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'consecutive_errors': _error_count
                }
            )
            return 0


async def aggregate_daily() -> int:
    """
    Агрегировать телеметрию по дням из telemetry_agg_1h.
    
    Returns:
        Количество созданных записей
    """
    # Проверяем error backoff перед началом агрегации
    if await _check_error_backoff():
        return 0
    
    with AGGREGATION_LAT.labels(type="daily").time():
        try:
            last_ts = await get_last_ts("daily")
            
            # Если нет последней метки, берём последние 7 дней
            if last_ts is None:
                last_ts = utcnow() - timedelta(days=7)
            
            # Агрегируем данные из telemetry_agg_1h
            rows = await fetch(
                """
                INSERT INTO telemetry_daily (
                    zone_id, node_id, channel, metric_type,
                    value_avg, value_min, value_max, value_median, sample_count, date
                )
                SELECT 
                    zone_id,
                    node_id,
                    channel,
                    metric_type,
                    AVG(value_avg)::float as value_avg,
                    MIN(value_min)::float as value_min,
                    MAX(value_max)::float as value_max,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_avg)::float as value_median,
                    SUM(sample_count)::int as sample_count,
                    DATE(ts) as date
                FROM telemetry_agg_1h
                WHERE ts > $1 AND ts <= NOW()
                GROUP BY zone_id, node_id, channel, metric_type, DATE(ts)
                ON CONFLICT (zone_id, node_id, channel, metric_type, date) 
                DO UPDATE SET
                    value_avg = EXCLUDED.value_avg,
                    value_min = EXCLUDED.value_min,
                    value_max = EXCLUDED.value_max,
                    value_median = EXCLUDED.value_median,
                    sample_count = EXCLUDED.sample_count
                RETURNING date
                """,
                last_ts,
            )
            
            count = len(rows) if rows else 0
            
            # Обновляем last_ts (используем максимальную дату как timestamp)
            if count > 0:
                max_date = max(row["date"] for row in rows)
                max_ts = datetime.combine(max_date, datetime.min.time())
                await update_last_ts("daily", max_ts)
            
            AGGREGATION_RECORDS.labels(type="daily").inc(count)
            logger.info(f"Aggregated daily: {count} records")
            
            # Сбрасываем счетчик ошибок при успехе
            await _record_success()
            
            return count
        except Exception as e:
            AGGREGATION_ERRORS.labels(type="daily").inc()
            await _record_error()
            logger.error(
                f"Error aggregating daily: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'consecutive_errors': _error_count
                }
            )
            return 0


async def run_aggregation():
    """Запустить все агрегации."""
    logger.info("Starting telemetry aggregation...")
    
    # Агрегируем по порядку: 1m -> 1h -> daily
    count_1m = await aggregate_1m()
    AGGREGATION_RUNS.labels(type="1m").inc()
    
    # Агрегируем 1h только если есть новые данные в 1m
    if count_1m > 0:
        count_1h = await aggregate_1h()
        AGGREGATION_RUNS.labels(type="1h").inc()
        
        # Агрегируем daily только если есть новые данные в 1h
        if count_1h > 0:
            count_daily = await aggregate_daily()
            AGGREGATION_RUNS.labels(type="daily").inc()
    
    logger.info("Telemetry aggregation completed")


async def cleanup_old_data():
    """
    Очистка старых данных согласно retention policy.
    
    Retention policy:
    - telemetry_samples: 90 дней (храним raw данные 3 месяца)
    - telemetry_agg_1m: 30 дней (храним минутные агрегаты 1 месяц)
    - telemetry_agg_1h: 365 дней (храним часовые агрегаты 1 год)
    - telemetry_daily: бессрочно (дневные агрегаты храним всегда)
    """
    with CLEANUP_LAT.time():
        try:
            CLEANUP_RUNS.inc()
            s = get_settings()
            
            # Retention periods (в днях)
            retention_samples_days = int(os.getenv('RETENTION_SAMPLES_DAYS', '90'))
            retention_1m_days = int(os.getenv('RETENTION_1M_DAYS', '30'))
            retention_1h_days = int(os.getenv('RETENTION_1H_DAYS', '365'))
            
            cutoff_samples = utcnow() - timedelta(days=retention_samples_days)
            cutoff_1m = utcnow() - timedelta(days=retention_1m_days)
            cutoff_1h = utcnow() - timedelta(days=retention_1h_days)
            
            # Удаляем старые raw samples
            deleted_samples = await execute(
                """
                DELETE FROM telemetry_samples
                WHERE ts < $1
                """,
                cutoff_samples,
            )
            deleted_samples_count = int(deleted_samples.split()[-1]) if deleted_samples and 'DELETE' in deleted_samples else 0
            if deleted_samples_count > 0:
                CLEANUP_DELETED.labels(table="telemetry_samples").inc(deleted_samples_count)
                logger.info(f"Deleted {deleted_samples_count} old telemetry_samples (older than {retention_samples_days} days)")
            
            # Удаляем старые 1m агрегаты
            deleted_1m = await execute(
                """
                DELETE FROM telemetry_agg_1m
                WHERE ts < $1
                """,
                cutoff_1m,
            )
            deleted_1m_count = int(deleted_1m.split()[-1]) if deleted_1m and 'DELETE' in deleted_1m else 0
            if deleted_1m_count > 0:
                CLEANUP_DELETED.labels(table="telemetry_agg_1m").inc(deleted_1m_count)
                logger.info(f"Deleted {deleted_1m_count} old telemetry_agg_1m records (older than {retention_1m_days} days)")
            
            # Удаляем старые 1h агрегаты
            deleted_1h = await execute(
                """
                DELETE FROM telemetry_agg_1h
                WHERE ts < $1
                """,
                cutoff_1h,
            )
            deleted_1h_count = int(deleted_1h.split()[-1]) if deleted_1h and 'DELETE' in deleted_1h else 0
            if deleted_1h_count > 0:
                CLEANUP_DELETED.labels(table="telemetry_agg_1h").inc(deleted_1h_count)
                logger.info(f"Deleted {deleted_1h_count} old telemetry_agg_1h records (older than {retention_1h_days} days)")
            
            # telemetry_daily не удаляем (храним бессрочно)
            
            return {
                'samples_deleted': deleted_samples_count,
                '1m_deleted': deleted_1m_count,
                '1h_deleted': deleted_1h_count,
            }
        except Exception as e:
            logger.error(
                f"Error cleaning up old data: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
            )
            return None


async def main():
    """Главный цикл агрегатора."""
    s = get_settings()
    
    # Запускаем Prometheus metrics сервер
    start_http_server(9404)  # Prometheus metrics
    
    # Интервал агрегации (по умолчанию каждые 5 минут)
    aggregation_interval_seconds = int(os.getenv('AGGREGATION_INTERVAL_SECONDS', '300'))
    
    # Интервал очистки старых данных (по умолчанию раз в день)
    cleanup_interval_seconds = int(os.getenv('CLEANUP_INTERVAL_SECONDS', '86400'))  # 24 часа
    
    logger.info(f"Telemetry aggregator started (interval: {aggregation_interval_seconds}s, cleanup: {cleanup_interval_seconds}s)")
    
    last_cleanup = utcnow()
    
    while True:
        try:
            await run_aggregation()
            
            # Периодически запускаем очистку старых данных
            now = utcnow()
            if (now - last_cleanup).total_seconds() >= cleanup_interval_seconds:
                await cleanup_old_data()
                last_cleanup = now
            
            # Сбрасываем счетчик ошибок при успешном цикле
            await _record_success()
        except Exception as e:
            await _record_error()
            logger.error(
                f"Error in aggregation cycle: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'consecutive_errors': _error_count
                }
            )
        
        # Применяем backoff: если активен, используем его вместо обычного интервала
        if _backoff_until and utcnow() < _backoff_until:
            backoff_remaining = (_backoff_until - utcnow()).total_seconds()
            # Ждем до окончания backoff или минимальный интервал
            sleep_time = min(backoff_remaining, aggregation_interval_seconds)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(aggregation_interval_seconds)


if __name__ == "__main__":
    import os
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]  # Явно указываем stdout для Docker
    )
    asyncio.run(main())
