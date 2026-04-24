"""Pytest session bootstrap для AE3-Lite.

Safety rails:
- integration-тесты AE3 пишут/удаляют в таблицы PostgreSQL (zones, greenhouses,
  ae_tasks, ae_commands и т.д.);
- если они запущены против `hydro_dev`, эти INSERT/DELETE смешиваются с
  реальными данными dev-прогона и оставляют мусор (test fixture только
  частично чистит за собой);
- поэтому здесь **жёстко** форсируем `PG_DB=hydro_test` на уровне process env
  **до** любого импорта `common.db`, чтобы asyncpg pool создавался уже в
  test-БД.

При необходимости перекрыть имя (например, CI test-db) выставьте
`AE3_PYTEST_DB` явно — оно имеет приоритет над дефолтным `hydro_test`.

Предусловия: hydro_test DB создана и на неё применены laravel миграции.
См. `Makefile` target `test-db-init`.
"""

from __future__ import annotations

import os
import uuid

_DEFAULT_TEST_DB = "hydro_test"
_OVERRIDE_ENV_VAR = "AE3_PYTEST_DB"
_FORBIDDEN_DBS = {"hydro_dev", "hydro_prod", "hydro"}


def _select_test_db() -> str:
    override = os.environ.get(_OVERRIDE_ENV_VAR, "").strip()
    candidate = override or _DEFAULT_TEST_DB
    if candidate in _FORBIDDEN_DBS:
        raise RuntimeError(
            f"AE3 pytest attempted to use forbidden DB '{candidate}'. "
            f"Set {_OVERRIDE_ENV_VAR} to a dedicated test database."
        )
    return candidate


# Применяем override на module-import (до collection), чтобы любой
# последующий import пути, который создаст asyncpg pool, уже видел
# правильное имя БД. pytest гарантирует загрузку conftest.py до тестовых
# модулей.
_TEST_DB = _select_test_db()
os.environ["PG_DB"] = _TEST_DB
os.environ["DB_DATABASE"] = _TEST_DB
# application_name помогает отличить test-коннекты от live-сервиса в pg_stat_activity.
os.environ.setdefault(
    "PG_APP_NAME",
    f"hydro:ae3-pytest-{uuid.uuid4().hex[:8]}",
)

# AE3 runtime валидирует токены при module-level импорте ae3lite.runtime.app
# (там `app = create_app()`). Collection упадёт, если токены отсутствуют.
# Ставим безопасные дефолты только для pytest, чтобы CI-шаги без отдельного
# секрет-ввода (smoke, contract) могли собрать тесты. Реальные прод/docker
# значения приходят из env и перекрывают дефолты через setdefault.
os.environ.setdefault("HISTORY_LOGGER_API_TOKEN", "pytest-history-logger-token")
os.environ.setdefault("AE_API_TOKEN", "pytest-ae-api-token")


# ---------------------------------------------------------------------------
# asyncpg pool cleanup между тестами.
#
# `common.db.get_pool()` кеширует asyncpg pool per event loop. pytest-asyncio
# (в режиме asyncio_mode=auto) по умолчанию даёт каждому async-тесту свой
# event loop. Если pool не закрывать, каждый тест оставляет висящие
# connections в PostgreSQL — в CI это быстро упирается в стандартный
# max_connections=100 и даёт TooManyConnectionsError.
#
# Локально в docker-dev это не проявляется, т.к. там max_connections=200 и
# тесты идут с одним процессом, но CI-runner стартует postgres с дефолтом,
# поэтому fixture-уровневая очистка нужна всегда.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _close_ae3_db_pool_after_test():
    yield
    try:
        import common.db as _db
    except Exception:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    pool = _db._get_pool_for_loop(loop)
    if pool is None:
        return
    if not _db._drop_pool_for_loop(loop, pool):
        return
    try:
        await pool.close()
    except Exception:
        pass
