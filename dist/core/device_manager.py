# -*- coding: utf-8 -*-
import subprocess
import weakref
from core.uiautomator import Uiautomator
from util.log_util import TempLog
from conf import GlobalConfig

# 设备实例缓存（弱引用，避免内存泄漏）
DEVICE_CACHE = weakref.WeakValueDictionary()


class DeviceManager:
    @staticmethod
    def get_device_list() -> list[dict]:
        """获取在线设备列表（ADB查询）"""
        log = TempLog()
        try:
            result = subprocess.run(
                [GlobalConfig["device"]["adb_path"], "devices"],
                capture_output=True, text=True, encoding="utf-8"
            )
            if result.returncode != 0:
                log.error(f"ADB查询设备失败：{result.stderr}")
                return []

            # 解析ADB输出（跳过首行和空行）
            lines = [line.strip() for line in result.stdout.split("\n") if line.strip()]
            if len(lines) <= 1:
                log.info("无在线设备")
                return []

            devices = []
            for line in lines[1:]:
                device_id, status = line.split("\t")
                if status == "device":  # 仅保留在线设备
                    devices.append({
                        "device_id": device_id,
                        "status": "online",
                        "atx_version": DeviceManager._get_atx_version(device_id)
                    })
            log.info(f"获取在线设备{len(devices)}个：{[d['device_id'] for d in devices]}")
            return devices
        except Exception as e:
            log.error(f"获取设备列表失败：{str(e)}", exc_info=True)
            return []

    @staticmethod
    def _get_atx_version(device_id: str) -> str:
        """获取设备atx-agent版本（不存在则返回"unknown"）"""
        try:
            result = subprocess.run(
                [GlobalConfig["device"]["adb_path"], "-s", device_id,
                 "shell", "/data/local/tmp/atx-agent", "version"],
                capture_output=True, text=True, encoding="utf-8", timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except:
            return "unknown"

    @staticmethod
    def get_uiautomator_instance(device_id: str, task_id: str) -> Uiautomator:
        """
        获取Uiautomator实例（缓存优先，不存在则新建）
        :param device_id: 设备ID
        :param task_id: 任务ID（用于日志）
        :return: Uiautomator实例（确保非None）
        """
        from util.log_util import LogUtil

        # 1. 检查缓存
        if device_id in DEVICE_CACHE:
            instance = DEVICE_CACHE[device_id]
            if instance.initialized:
                instance.log.info(f"从缓存获取设备{device_id}实例")
                return instance

        # 2. 新建实例（带日志）
        log_util = LogUtil(device_id=device_id, task_id=task_id, logger_name=f"device_{device_id}")
        instance = Uiautomator(device_id=device_id, log_util=log_util)

        # 3. 加入缓存
        DEVICE_CACHE[device_id] = instance
        return instance

    @staticmethod
    def release_device(device_id: str) -> None:
        """释放设备实例（清理缓存）"""
        if device_id in DEVICE_CACHE:
            instance = DEVICE_CACHE[device_id]
            instance.log.info(f"释放设备{device_id}实例")
            del DEVICE_CACHE[device_id]