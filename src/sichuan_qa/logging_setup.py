#!/usr/bin/env python3
# coding: utf-8
"""统一日志。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from sichuan_qa.config import ROOT, get_settings

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "sichuan_qa.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handlers.append(file_handler)

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
