"""统一日志配置模块"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from config.settings import settings


class JsonLogFormatter(logging.Formatter):
    """输出结构化 JSON 日志，兼容 LOG_FORMAT=json 的运行时配置。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_formatter(log_format: str) -> logging.Formatter:
    fmt = str(log_format or "").strip()
    if fmt.lower() == "json":
        return JsonLogFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    try:
        return logging.Formatter(fmt=fmt or "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    except ValueError:
        # 配置被写成了非 logging.Formatter 兼容格式时，回退到安全默认值。
        return logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logging(service_name: str = "quantmind"):
    """设置日志配置

    Args:
        service_name: 服务名称，用于日志文件命名
    """
    # 创建根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.logging.log_level.upper()))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 创建格式器
    formatter = _build_formatter(settings.logging.log_format)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # 文件处理器（如果配置了日志文件）
    if settings.logging.log_file:
        log_file = Path(settings.logging.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=settings.logging.max_log_size,
            backupCount=settings.logging.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

    # 为特定服务创建日志文件
    try:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        service_log_file = logs_dir / f"{service_name}.log"
        service_handler = logging.handlers.RotatingFileHandler(
            filename=service_log_file,
            maxBytes=settings.logging.max_log_size,
            backupCount=settings.logging.backup_count,
            encoding="utf-8",
        )
        service_handler.setFormatter(formatter)
        service_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(service_handler)
    except Exception as e:
        sys.stderr.write(f"Failed to setup file logging: {e}\n")

    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.info(f"Logging configured for service: {service_name}")


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器

    Args:
        name: 日志器名称

    Returns:
        配置好的日志器实例
    """
    return logging.getLogger(name)


class LoggerMixin:
    """日志器混入类，为类提供日志功能"""

    @property
    def logger(self) -> logging.Logger:
        """获取当前类的日志器"""
        return get_logger(self.__class__.__name__)
