import os
import sys
from pathlib import Path
from loguru import logger

from app.config import settings


def setup_logging():
    """
    Configure Loguru logger with custom format and log files
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Log format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Remove default handler
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.LOG_LEVEL,
        backtrace=True,
        diagnose=True,
    )
    
    # Add file handler
    logger.add(
        settings.LOG_FILE,
        format=log_format,
        level=settings.LOG_LEVEL,
        rotation="00:00",  # Rotate at midnight
        compression="zip",
        retention="30 days",
        backtrace=True,
        diagnose=True,
    )
    
    # Also add a separate error log
    logger.add(
        "logs/error.log",
        format=log_format,
        level="ERROR",
        rotation="10 MB",
        compression="zip",
        retention="30 days",
        backtrace=True,
        diagnose=True,
    )
    
    # Log startup message
    logger.info(f"Logging system initialized - Level: {settings.LOG_LEVEL}")
    
    return logger
