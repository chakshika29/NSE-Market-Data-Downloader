"""Logging configuration and helpers for NSE Market Data Downloader."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "nse_downloader",
    log_dir: str = "logs",
    log_file: str = "app.log",
    level: int = logging.INFO,
    console_output: bool = True,
) -> logging.Logger:
    """Configure and return a structured logger.

    Writes detailed logs to `log_dir/log_file` and optionally to console.
    Ensures log directories exist and prevents duplicate handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times if logger already configured
    if logger.handlers:
        return logger

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    full_log_file = log_path / log_file

    # File handler: structured with milliseconds and component
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(full_log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler: clean and readable for CLI output
    if console_output:
        console_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger
