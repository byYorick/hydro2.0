import logging
import os
import sys

from app import app, setup_signal_handlers
from common.env import get_settings


if __name__ == "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_value = getattr(logging, log_level, logging.INFO)
    uvicorn_log_level = "warning" if log_level == "WARN" else log_level.lower()
    logging.basicConfig(
        level=log_level_value,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger().setLevel(log_level_value)
    logging.getLogger("__main__").setLevel(log_level_value)
    logging.getLogger("main").setLevel(log_level_value)
    logging.getLogger("common.mqtt").setLevel(log_level_value)

    setup_signal_handlers()

    import uvicorn

    s = get_settings()

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["default"],
        },
        "loggers": {
            "uvicorn": {"level": "INFO"},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"level": "INFO"},
        },
    }

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=s.service_port,
        log_config=log_config,
        log_level=uvicorn_log_level,
    )
