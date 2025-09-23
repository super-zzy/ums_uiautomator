# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import logging
import os
import traceback  # 新增：导入 traceback 模块，用于打印异常堆栈
from datetime import datetime
from conf import GlobalConfig

LOG_ROOT = GlobalConfig["path"]["log_root_dir"]


class LogUtil:
    def __init__(self, device_id: str, task_id: str, logger_name: str = "automation"):
        """
        初始化日志工具（按设备+日期分目录，按任务ID分文件）
        :param device_id: 设备ID（用于日志目录分类）
        :param task_id: 任务ID（用于日志文件命名）
        :param logger_name: 日志器名称
        """
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # 避免重复添加处理器

        # 日志目录：LOG_ROOT/设备ID/日期（如 logs/AF8YVB1805003480/20240520）
        date_str = datetime.now().strftime("%Y%m%d")
        log_dir = os.path.join(LOG_ROOT, device_id, date_str)
        os.makedirs(log_dir, exist_ok=True)

        # 日志文件：任务ID.log（如 20240520123456_abc1.log）
        log_file = os.path.join(log_dir, f"{task_id}.log")

        # 控制台处理器（INFO级别）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)

        # 文件处理器（DEBUG级别，含详细信息）
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)

        # 添加处理器
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def debug(self, msg: str) -> None:
        self.logger.debug(msg)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str, exc_info: bool = False) -> None:
        self.logger.error(msg, exc_info=exc_info)  # exc_info=True时打印堆栈


# 降级日志（LogUtil初始化失败时使用）
class TempLog:
    @staticmethod
    def _log(level: str, msg: str, exc_info: bool = False) -> None:
        """基础日志打印方法，新增 exc_info 参数支持异常堆栈"""
        log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level.upper()}] {msg}"
        print(log_msg)
        # 若需要打印异常堆栈，调用 traceback.print_exc()
        if exc_info:
            print(f"[异常堆栈]：")
            traceback.print_exc()  # 打印当前异常的堆栈信息

    def debug(self, msg: str) -> None:
        self._log("debug", msg)

    def info(self, msg: str) -> None:
        self._log("info", msg)

    def warning(self, msg: str) -> None:
        self._log("warning", msg)

    def error(self, msg: str, exc_info: bool = False) -> None:
        """新增 exc_info 参数，匹配 LogUtil 的调用方式"""
        self._log("error", msg, exc_info=exc_info)
