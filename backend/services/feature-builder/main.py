"""
feature-builder — ML Phase 2 skeleton.

Назначение: единственный writer в zone_features_5m, ml_labels и
dose_response_events. Phase 2A (этот файл) содержит скелет с health/metrics
и poll-loop-заглушкой. Реальная логика сбора витрин — Phase 3.

См. doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md §6.
"""
import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, make_asgi_app

from common.logging_setup import install_exception_handlers, setup_standard_logging

logger = logging.getLogger(__name__)

# --- конфигурация ---
POLL_INTERVAL_SEC = int(os.getenv("FEATURE_BUILDER_POLL_INTERVAL_SEC", "60"))
LOOKBACK_HOURS = int(os.getenv("FEATURE_BUILDER_LOOKBACK_HOURS", "24"))
HORIZONS = [int(x) for x in os.getenv("FEATURE_BUILDER_HORIZONS", "5,15,60").split(",")]
MIN_VALID_RATIO = float(os.getenv("FEATURE_BUILDER_MIN_VALID_RATIO", "0.7"))
SCHEMA_VERSION = int(os.getenv("FEATURE_BUILDER_SCHEMA_VERSION", "1"))

PG_DSN = (
    f"postgresql://{os.getenv('PG_USER', 'hydro')}:{os.getenv('PG_PASS', 'hydro')}"
    f"@{os.getenv('PG_HOST', 'db')}:{os.getenv('PG_PORT', '5432')}"
    f"/{os.getenv('PG_DB', 'hydro_dev')}"
)

# --- метрики ---
FB_ROWS = Counter(
    "feature_builder_rows_written_total",
    "Rows written by feature-builder",
    ["table"],
)
FB_ERRORS = Counter(
    "feature_builder_errors_total",
    "Errors by stage",
    ["stage"],
)
FB_LAG = Gauge(
    "feature_builder_lag_seconds",
    "Lag of the last pipeline update vs now",
    ["pipeline"],
)
FB_POLL_RUNS = Counter(
    "feature_builder_poll_runs_total",
    "Poll-loop iterations",
)

# --- состояние ---
_pool: asyncpg.Pool | None = None
_shutdown = asyncio.Event()


async def _init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        PG_DSN,
        min_size=1,
        max_size=4,
        command_timeout=30,
    )
    logger.info("pg pool initialised")


async def _close_pool() -> None:
    if _pool is not None:
        await _pool.close()


async def _check_db() -> bool:
    """Простая проверка: БД доступна и ML-витрины существуют."""
    assert _pool is not None
    async with _pool.acquire() as conn:
        # NB: только структурная проверка, без чтения данных.
        row = await conn.fetchrow(
            """
            SELECT
                to_regclass('public.zone_features_5m')        AS features,
                to_regclass('public.ml_labels')               AS labels,
                to_regclass('public.ml_data_quality_windows') AS dq
            """
        )
        return all(row[k] is not None for k in ("features", "labels", "dq"))


async def _poll_once() -> None:
    """
    Одна итерация poll-loop. Phase 2A: no-op, только увеличивает счётчик.
    Phase 3: здесь будет реальная сборка zone_features_5m, ml_labels,
    dose_response_events, заполнение ml_data_quality_windows.
    """
    FB_POLL_RUNS.inc()
    # Phase 3 TODO: build_zone_features_5m(), build_ml_labels(),
    # build_dose_response_events(), apply_quality_rules().


async def _poll_loop() -> None:
    logger.info(
        "poll loop started interval=%ss horizons=%s schema_version=%s",
        POLL_INTERVAL_SEC, HORIZONS, SCHEMA_VERSION,
    )
    while not _shutdown.is_set():
        try:
            await _poll_once()
        except Exception as e:
            FB_ERRORS.labels(stage="poll").inc()
            logger.error("poll iteration failed: %s", e, exc_info=True)
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=POLL_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_standard_logging("feature-builder")
    install_exception_handlers("feature-builder", logger)
    await _init_pool()
    task = asyncio.create_task(_poll_loop(), name="feature-builder-poll")
    try:
        yield
    finally:
        _shutdown.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        await _close_pool()


app = FastAPI(title="feature-builder", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
async def healthz() -> dict:
    if _pool is None:
        return {"status": "starting"}
    try:
        async with _pool.acquire() as conn:
            await conn.execute("SELECT 1")
        schema_ok = await _check_db()
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

    return {
        "status": "ok" if schema_ok else "schema_missing",
        "schema_version": SCHEMA_VERSION,
        "poll_interval_sec": POLL_INTERVAL_SEC,
        "horizons": HORIZONS,
    }


@app.get("/readyz")
async def readyz() -> dict:
    health = await healthz()
    return health


def _install_signal_handlers() -> None:
    """Gracefully выключаем poll-loop по SIGTERM/SIGINT (supervisor stopasgroup)."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown.set)
        except NotImplementedError:
            # Windows dev-кейсы
            pass


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("FEATURE_BUILDER_PORT", "9410"))
    # Передаём объект app напрямую (НЕ строкой "main:app"), иначе uvicorn
    # реимпортирует модуль — повторная регистрация prometheus-метрик упадёт
    # с "Duplicated timeseries in CollectorRegistry".
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
