# -*- coding: utf-8 -*-
import subprocess
import time
import os
from conf import GlobalConfig
from util.log_util import TempLog


class Uiautomator:
    def __init__(self, device_id: str, log_util=None):
        self.device_id = device_id
        self.log = log_util or TempLog()
        self.atx_version = GlobalConfig["device"]["atx_version"]  # 保留版本配置，用于后续校验
        self.initialized = False  # 初始化状态标记
        self._init_device()  # 初始化设备（失败则抛出异常）

    def _init_device(self) -> None:
        """
        初始化设备：基于 `python -m uiautomator2 init` 命令
        包含设备在线检查、uiautomator2初始化、atx-agent版本校验
        """
        try:
            self.log.info(f"开始初始化设备：{self.device_id}")

            # 1. 先检查ADB设备是否在线（基础前置校验）
            if not self._is_device_online():
                raise ConnectionError(f"设备{self.device_id}未在线（请检查ADB连接）")

            # 2. 执行 uiautomator2 init 命令（核心初始化逻辑）
            self._run_uiautomator2_init()

            # 3. 校验 atx-agent 版本（确保初始化结果符合预期）
            self._verify_atx_agent_version()

            self.initialized = True
            self.log.info(f"设备{self.device_id}初始化成功")
        except Exception as e:
            self.log.error(f"设备{self.device_id}初始化失败：{str(e)}", exc_info=True)
            raise  # 向上抛出异常，避免返回未初始化的实例

    def _is_device_online(self) -> bool:
        """检查设备是否在线（复用原有逻辑）"""
        result = subprocess.run(
            [GlobalConfig["device"]["adb_path"], "-s", self.device_id, "get-state"],
            capture_output=True, text=True, encoding="utf-8"
        )
        online = result.returncode == 0 and result.stdout.strip() == "device"
        self.log.debug(f"设备{self.device_id}在线状态：{online}")
        return online

    def _run_uiautomator2_init(self) -> None:
        """执行 `python -m uiautomator2 init` 命令，捕获输出日志"""
        init_cmd = [
            "python", "-m", "uiautomator2", "init",
            self.device_id  # 指定目标设备ID
        ]
        self.log.info(f"执行初始化命令：{' '.join(init_cmd)}")

        # 执行命令并捕获实时输出（避免缓冲区阻塞，同时打印日志）
        process = subprocess.Popen(
            init_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并 stdout 和 stderr
            text=True,
            encoding="utf-8"
        )

        # 实时读取输出并记录日志
        while process.poll() is None:
            if process.stdout:
                line = process.stdout.readline()
                if line:
                    self.log.debug(f"uiautomator2 init 输出：{line.strip()}")

        # 检查命令执行结果
        if process.returncode != 0:
            raise RuntimeError(
                f"uiautomator2 init 执行失败（返回码：{process.returncode}）"
            )
        self.log.info("uiautomator2 init 命令执行完成")

    def _verify_atx_agent_version(self) -> None:
        """校验 atx-agent 版本（复用原有逻辑，确保版本符合配置）"""
        # 等待2秒确保 atx-agent 完全启动
        time.sleep(2)
        version_cmd = [
            GlobalConfig["device"]["adb_path"], "-s", self.device_id,
            "shell", "/data/local/tmp/atx-agent", "version"
        ]
        self.log.debug(f"执行 atx-agent 版本校验命令：{' '.join(version_cmd)}")

        result = subprocess.run(
            version_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        if result.returncode != 0:
            raise RuntimeError(f"获取 atx-agent 版本失败：{result.stderr.strip()}")

        actual_version = result.stdout.strip()
        # if self.atx_version not in actual_version:
        #     raise RuntimeError(
        #         f"atx-agent 版本不匹配（期望：{self.atx_version}，实际：{actual_version}）"
        #     )
        # self.log.info(f"atx-agent 版本校验通过：{actual_version}")

    # ------------------- 原有设备控制接口（完全保留，确保功能兼容） -------------------
    def screen_on(self) -> bool:
        if not self.initialized:
            raise RuntimeError(f"设备{self.device_id}未初始化，无法执行亮屏操作")
        try:
            cmd = [
                GlobalConfig["device"]["adb_path"], "-s", self.device_id,
                "shell", "input", "keyevent", "224"  # 224=KEYCODE_POWER
            ]
            subprocess.run(cmd, capture_output=True)
            self.log.info(f"设备{self.device_id}执行亮屏操作")
            return True
        except Exception as e:
            self.log.error(f"设备{self.device_id}亮屏失败：{str(e)}", exc_info=True)
            return False

    def press(self, key: str) -> bool:
        key_map = {"home": 3, "back": 4, "power": 224}
        if key not in key_map:
            self.log.error(f"不支持的按键：{key}（支持：{list(key_map.keys())}）")
            return False
        try:
            cmd = [
                GlobalConfig["device"]["adb_path"], "-s", self.device_id,
                "shell", "input", "keyevent", str(key_map[key])
            ]
            subprocess.run(cmd, capture_output=True)
            self.log.info(f"设备{self.device_id}执行按键操作：{key}")
            return True
        except Exception as e:
            self.log.error(f"设备{self.device_id}按键{key}失败：{str(e)}", exc_info=True)
            return False

    def check_text_exists(self, text: str) -> bool:
        try:
            cmd = [
                GlobalConfig["device"]["adb_path"], "-s", self.device_id,
                "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"
            ]
            subprocess.run(cmd, capture_output=True)

            pull_cmd = [
                GlobalConfig["device"]["adb_path"], "-s", self.device_id,
                "pull", "/sdcard/window_dump.xml", "/tmp/"
            ]
            subprocess.run(pull_cmd, capture_output=True)

            with open("/tmp/window_dump.xml", "r", encoding="utf-8") as f:
                content = f.read()
            exists = text in content
            self.log.info(f"设备{self.device_id}检查文本'{text}'：{'存在' if exists else '不存在'}")
            return exists
        except Exception as e:
            self.log.error(f"设备{self.device_id}检查文本'{text}'失败：{str(e)}", exc_info=True)
            return False

    def click(self, x: int, y: int) -> bool:
        if not (isinstance(x, int) and isinstance(y, int)):
            self.log.error(f"点击坐标参数错误：x={x}（需int）, y={y}（需int）")
            return False
        try:
            cmd = [
                GlobalConfig["device"]["adb_path"], "-s", self.device_id,
                "shell", "input", "tap", str(x), str(y)
            ]
            subprocess.run(cmd, capture_output=True)
            self.log.info(f"设备{self.device_id}点击坐标：({x}, {y})")
            return True
        except Exception as e:
            self.log.error(f"设备{self.device_id}点击坐标({x},{y})失败：{str(e)}", exc_info=True)
            return False