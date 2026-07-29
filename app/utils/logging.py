"""Configuración de logging rotativo para toda la aplicación."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "analizador_bancario"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def configure_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configura (una sola vez) el logger raíz de la aplicación."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "analizador_bancario.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    full_name = LOGGER_NAME if not name else f"{LOGGER_NAME}.{name}"
    return logging.getLogger(full_name)
