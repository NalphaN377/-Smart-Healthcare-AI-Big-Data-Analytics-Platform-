"""统一日志配置：控制台 + 可选滚动文件输出。"""
import logging
import sys
from logging.handlers import RotatingFileHandler

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str, level: int = logging.INFO, log_file: str = None) -> logging.Logger:
    """获取命名 logger，重复调用不会重复添加 handler。

    Args:
        name: logger 名称（通常传模块名 __name__）。
        level: 日志级别。
        log_file: 可选，滚动日志文件路径。
    """
    logger = logging.getLogger(name)
    if logger.handlers:  # 已初始化，直接复用
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(_DEFAULT_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
