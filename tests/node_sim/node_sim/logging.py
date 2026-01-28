"""
Настройка логирования для node-sim.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", format_string: Optional[str] = None):
    """
    Настроить логирование.
    
    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        format_string: Формат строки логов (опционально)
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер.
    
    Args:
        name: Имя логгера
    
    Returns:
        Logger
    """
    return logging.getLogger(name)

