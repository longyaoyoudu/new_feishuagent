import sys
from loguru import logger
from pathlib import Path
from typing import Optional

from config import settings


def setup_logger(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    encoding: str = "utf-8",
) -> None:
    log_level = log_level or settings.LOG_LEVEL
    log_file = log_file or settings.LOG_FILE

    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        encoding=encoding,
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"日志系统初始化完成，日志级别: {log_level}")
    logger.info(f"日志文件路径: {log_path.absolute()}")


__all__ = ["setup_logger", "logger"]
