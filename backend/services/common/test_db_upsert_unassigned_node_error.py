from unittest.mock import AsyncMock, patch

import pytest

import common.db as db


@pytest.mark.asyncio
async def test_upsert_unassigned_node_error_updates_existing_row():
    execute_mock = AsyncMock(return_value="UPDATE 1")

    with patch.object(db, "execute", execute_mock):
        await db.upsert_unassigned_node_error(
            hardware_id="esp32-test-1",
            error_message="error",
            error_code="E1",
            severity="ERROR",
            topic="hydro/gh-temp/zn-temp/esp32-test-1/error",
            last_payload={"code": "E1"},
        )

    assert execute_mock.await_count == 1
    first_query = execute_mock.await_args_list[0].args[0]
    assert "UPDATE unassigned_node_errors" in first_query


@pytest.mark.asyncio
async def test_upsert_unassigned_node_error_inserts_when_update_misses():
    execute_mock = AsyncMock(side_effect=["UPDATE 0", "INSERT 0 1"])

    with patch.object(db, "execute", execute_mock):
        await db.upsert_unassigned_node_error(
            hardware_id="esp32-test-2",
            error_message="error",
            error_code="E2",
            severity="ERROR",
            topic="hydro/gh-temp/zn-temp/esp32-test-2/error",
            last_payload={"code": "E2"},
        )

    assert execute_mock.await_count == 2
    queries = [item.args[0] for item in execute_mock.await_args_list]
    assert "UPDATE unassigned_node_errors" in queries[0]
    assert "INSERT INTO unassigned_node_errors" in queries[1]


@pytest.mark.asyncio
async def test_upsert_unassigned_node_error_retries_update_after_unique_violation():
    class _PgUniqueViolation(Exception):
        sqlstate = "23505"

    execute_mock = AsyncMock(side_effect=["UPDATE 0", _PgUniqueViolation("dup"), "UPDATE 1"])

    with patch.object(db, "execute", execute_mock):
        await db.upsert_unassigned_node_error(
            hardware_id="esp32-test-3",
            error_message="error",
            error_code="E3",
            severity="ERROR",
            topic="hydro/gh-temp/zn-temp/esp32-test-3/error",
            last_payload={"code": "E3"},
        )

    assert execute_mock.await_count == 3
    queries = [item.args[0] for item in execute_mock.await_args_list]
    assert "UPDATE unassigned_node_errors" in queries[0]
    assert "INSERT INTO unassigned_node_errors" in queries[1]
    assert "UPDATE unassigned_node_errors" in queries[2]
