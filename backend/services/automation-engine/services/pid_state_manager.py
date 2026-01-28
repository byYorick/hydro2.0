"""
PID State Manager - управление состоянием PID контроллеров.
Сохраняет и восстанавливает состояние PID при перезапуске сервиса.
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from common.db import execute, fetch
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig

logger = logging.getLogger(__name__)


class PidStateManager:
    """Управление состоянием PID контроллеров."""
    
    async def save_pid_state(
        self,
        zone_id: int,
        pid_type: str,
        pid: AdaptivePid
    ) -> None:
        """
        Сохранить состояние PID в БД.
        
        Args:
            zone_id: ID зоны
            pid_type: Тип PID ('ph' или 'ec')
            pid: Экземпляр PID контроллера
        """
        try:
            stats_dict = {
                'corrections_count': pid.stats.corrections_count,
                'total_output': pid.stats.total_output,
                'max_error': pid.stats.max_error,
                'avg_error': pid.stats.avg_error,
                'time_in_dead_ms': pid.stats.time_in_dead_ms,
                'time_in_close_ms': pid.stats.time_in_close_ms,
                'time_in_far_ms': pid.stats.time_in_far_ms
            }
            
            await execute(
                """
                INSERT INTO pid_state (
                    zone_id, pid_type, integral, prev_error, 
                    last_output_ms, stats, current_zone, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                ON CONFLICT (zone_id, pid_type) DO UPDATE
                SET integral = EXCLUDED.integral,
                    prev_error = EXCLUDED.prev_error,
                    last_output_ms = EXCLUDED.last_output_ms,
                    stats = EXCLUDED.stats,
                    current_zone = EXCLUDED.current_zone,
                    updated_at = NOW()
                """,
                zone_id,
                pid_type,
                pid.integral,
                pid.prev_error,
                pid.last_output_ms,
                json.dumps(stats_dict),
                pid.current_zone.value
            )
            
            logger.debug(
                f"Zone {zone_id}: PID {pid_type} state saved",
                extra={'zone_id': zone_id, 'pid_type': pid_type}
            )
        except Exception as e:
            logger.warning(
                f"Zone {zone_id}: Failed to save PID {pid_type} state: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'pid_type': pid_type}
            )
    
    async def load_pid_state(
        self,
        zone_id: int,
        pid_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Загрузить состояние PID из БД.
        
        Args:
            zone_id: ID зоны
            pid_type: Тип PID ('ph' или 'ec')
        
        Returns:
            Dict с состоянием PID или None
        """
        try:
            rows = await fetch(
                """
                SELECT integral, prev_error, last_output_ms, stats, current_zone
                FROM pid_state
                WHERE zone_id = $1 AND pid_type = $2
                """,
                zone_id,
                pid_type
            )
            
            if rows and len(rows) > 0:
                row = rows[0]
                stats = json.loads(row['stats']) if row['stats'] else {}
                
                return {
                    'integral': float(row['integral']) if row['integral'] is not None else 0.0,
                    'prev_error': float(row['prev_error']) if row['prev_error'] is not None else None,
                    'last_output_ms': int(row['last_output_ms']) if row['last_output_ms'] is not None else 0,
                    'stats': stats,
                    'current_zone': row.get('current_zone')
                }
            
            return None
        except Exception as e:
            logger.warning(
                f"Zone {zone_id}: Failed to load PID {pid_type} state: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'pid_type': pid_type}
            )
            return None
    
    async def restore_pid_state(
        self,
        zone_id: int,
        pid_type: str,
        pid: AdaptivePid
    ) -> bool:
        """
        Восстановить состояние PID из БД.
        
        Args:
            zone_id: ID зоны
            pid_type: Тип PID ('ph' или 'ec')
            pid: Экземпляр PID контроллера
        
        Returns:
            True если состояние восстановлено, False в противном случае
        """
        state = await self.load_pid_state(zone_id, pid_type)
        
        if state is None:
            return False
        
        try:
            # Восстанавливаем состояние
            pid.integral = state['integral']
            pid.prev_error = state['prev_error']
            pid.last_output_ms = state['last_output_ms']
            
            # Восстанавливаем статистику
            if state['stats']:
                stats = state['stats']
                pid.stats.corrections_count = stats.get('corrections_count', 0)
                pid.stats.total_output = stats.get('total_output', 0.0)
                pid.stats.max_error = stats.get('max_error', 0.0)
                pid.stats.avg_error = stats.get('avg_error', 0.0)
                pid.stats.time_in_dead_ms = stats.get('time_in_dead_ms', 0)
                pid.stats.time_in_close_ms = stats.get('time_in_close_ms', 0)
                pid.stats.time_in_far_ms = stats.get('time_in_far_ms', 0)
            
            # Восстанавливаем текущую зону
            if state.get('current_zone'):
                from utils.adaptive_pid import PidZone
                try:
                    pid.current_zone = PidZone(state['current_zone'])
                except ValueError:
                    pass  # Используем значение по умолчанию
            
            logger.info(
                f"Zone {zone_id}: PID {pid_type} state restored",
                extra={'zone_id': zone_id, 'pid_type': pid_type}
            )
            return True
        except Exception as e:
            logger.warning(
                f"Zone {zone_id}: Failed to restore PID {pid_type} state: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'pid_type': pid_type}
            )
            return False
    
    async def save_all_pid_states(
        self,
        ph_pids: Dict[int, AdaptivePid],
        ec_pids: Dict[int, AdaptivePid]
    ) -> None:
        """
        Сохранить состояние всех PID контроллеров.
        
        Args:
            ph_pids: Словарь zone_id -> PH PID
            ec_pids: Словарь zone_id -> EC PID
        """
        tasks = []
        
        for zone_id, pid in ph_pids.items():
            tasks.append(self.save_pid_state(zone_id, 'ph', pid))
        
        for zone_id, pid in ec_pids.items():
            tasks.append(self.save_pid_state(zone_id, 'ec', pid))
        
        if tasks:
            import asyncio
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Saved PID state for {len(ph_pids)} PH and {len(ec_pids)} EC controllers")


