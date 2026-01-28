#!/usr/bin/env python3
"""
Скрипт для добавления тестовых данных в БД для интеграционных тестов.
Создает тестовый greenhouse, zone и ноды.
"""

import asyncio
import httpx
import logging
import os
import sys

# Добавляем путь к сервисам
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

from common.db import execute, fetch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Тестовые данные
TEST_GH_UID = "gh-test-1"
TEST_ZONE_UID = "zn-test-1"
TEST_NODES = {
    "ph_node": {"uid": "nd-ph-test-1", "type": "ph"},
    "ec_node": {"uid": "nd-ec-test-1", "type": "ec"},
    "pump_node": {"uid": "nd-pump-test-1", "type": "pump"},
    "climate_node": {"uid": "nd-climate-test-1", "type": "climate"},
    "relay_node": {"uid": "nd-relay-test-1", "type": "relay"},
    "light_node": {"uid": "nd-light-test-1", "type": "light"},
}


async def setup_test_data():
    """Создает тестовые данные в БД."""
    logger.info("Setting up test data in database...")
    
    try:
        # 1. Создаем тестовый greenhouse (если не существует)
        logger.info(f"Creating greenhouse: {TEST_GH_UID}")
        gh_result = await fetch(
            "SELECT id FROM greenhouses WHERE uid = $1",
            TEST_GH_UID
        )
        
        if not gh_result:
            await execute(
                """
                INSERT INTO greenhouses (uid, name, type, timezone, created_at, updated_at)
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                """,
                TEST_GH_UID,
                "Test Greenhouse",
                "indoor",
                "UTC"
            )
            logger.info(f"✓ Created greenhouse: {TEST_GH_UID}")
        else:
            logger.info(f"✓ Greenhouse already exists: {TEST_GH_UID}")
        
        # Получаем ID greenhouse
        gh_result = await fetch(
            "SELECT id FROM greenhouses WHERE uid = $1",
            TEST_GH_UID
        )
        gh_id = gh_result[0]['id']
        
        # 2. Создаем тестовую zone (если не существует)
        logger.info(f"Creating zone: {TEST_ZONE_UID}")
        zone_result = await fetch(
            "SELECT id FROM zones WHERE uid = $1",
            TEST_ZONE_UID
        )
        
        if not zone_result:
            await execute(
                """
                INSERT INTO zones (greenhouse_id, uid, name, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                """,
                gh_id,
                TEST_ZONE_UID,
                "Test Zone"
            )
            logger.info(f"✓ Created zone: {TEST_ZONE_UID}")
        else:
            logger.info(f"✓ Zone already exists: {TEST_ZONE_UID}")
        
        # Получаем ID zone
        zone_result = await fetch(
            "SELECT id FROM zones WHERE uid = $1",
            TEST_ZONE_UID
        )
        zone_id = zone_result[0]['id']
        
        # 3. Создаем тестовые ноды
        created_count = 0
        for node_name, node_data in TEST_NODES.items():
            node_uid = node_data["uid"]
            node_type = node_data["type"]
            
            logger.info(f"Creating node: {node_uid} (type: {node_type})")
            
            # Проверяем, существует ли нода
            node_result = await fetch(
                "SELECT id FROM nodes WHERE uid = $1",
                node_uid
            )
            
            if not node_result:
                await execute(
                    """
                    INSERT INTO nodes (
                        zone_id, uid, name, type, status, lifecycle_state,
                        error_count, warning_count, critical_count,
                        created_at, updated_at, last_seen_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW(), NOW())
                    """,
                    zone_id,
                    node_uid,
                    f"Test {node_name}",
                    node_type,
                    "online",
                    "ACTIVE",
                    0,  # error_count
                    0,  # warning_count
                    0   # critical_count
                )
                logger.info(f"✓ Created node: {node_uid}")
                created_count += 1
            else:
                logger.info(f"✓ Node already exists: {node_uid}")
                # Обновляем метрики на 0, если они были
                await execute(
                    """
                    UPDATE nodes 
                    SET error_count = 0, warning_count = 0, critical_count = 0,
                        status = 'online', lifecycle_state = 'ACTIVE',
                        updated_at = NOW(), last_seen_at = NOW()
                    WHERE uid = $1
                    """,
                    node_uid
                )
        
        logger.info(f"\n✓ Setup complete! Created {created_count} new nodes, {len(TEST_NODES)} total nodes ready")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to setup test data: {e}", exc_info=True)
        return False


async def cleanup_test_data():
    """Удаляет тестовые данные из БД."""
    logger.info("Cleaning up test data from database...")
    
    try:
        # Удаляем ноды
        for node_name, node_data in TEST_NODES.items():
            node_uid = node_data["uid"]
            await execute("DELETE FROM nodes WHERE uid = $1", node_uid)
            logger.info(f"✓ Deleted node: {node_uid}")
        
        # Удаляем zone
        await execute("DELETE FROM zones WHERE uid = $1", TEST_ZONE_UID)
        logger.info(f"✓ Deleted zone: {TEST_ZONE_UID}")
        
        # Удаляем greenhouse
        await execute("DELETE FROM greenhouses WHERE uid = $1", TEST_GH_UID)
        logger.info(f"✓ Deleted greenhouse: {TEST_GH_UID}")
        
        logger.info("✓ Cleanup complete!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to cleanup test data: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup or cleanup test data for integration tests")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup test data instead of setup")
    args = parser.parse_args()
    
    if args.cleanup:
        asyncio.run(cleanup_test_data())
    else:
        asyncio.run(setup_test_data())

