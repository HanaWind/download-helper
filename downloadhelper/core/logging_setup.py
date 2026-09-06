"""日志初始化：在程序根目录 ./logs 下生成运行日志。

日志文件名格式：启动时年月日时分 + 4 位字母数字随机串，例如
``202609061802_7e6H.log``。
"""

from __future__ import annotations

import logging
import os
import random
import string
from datetime import datetime
from typing import Optional

# 程序根目录（含 main.py）：
#   downloadhelper/core/logging_setup.py -> downloadhelper/core -> downloadhelper -> 根
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(_ROOT, "logs")

_LOGGER_NAME = "HanaDownloadHelper"
_configured = False
_log_file: Optional[str] = None


def make_log_path() -> str:
    """按规范生成日志文件路径。"""
    ts = datetime.now().strftime("%Y%m%d%H%M")
    rand = "".join(random.choices(string.ascii_letters + string.digits, k=4))
    return os.path.join(LOG_DIR, f"{ts}_{rand}.log")


def setup_logging(level: int = logging.INFO, console: bool = True) -> logging.Logger:
    """初始化日志：文件 Handler + 可选控制台 Handler。幂等。"""
    global _configured, _log_file
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    _configured = True

    logger.setLevel(level)
    logger.propagate = False

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass

    _log_file = make_log_path()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = logging.FileHandler(_log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:  # 极端情况下日志文件不可写也不影响主程序
        logging.warning("无法创建日志文件：%s", exc)

    if console:
        stream = logging.StreamHandler()
        stream.setLevel(level)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    logger.info("日志初始化完成，日志文件：%s", _log_file)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def log_path() -> Optional[str]:
    return _log_file
