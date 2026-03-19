# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import Optional, List

from conf import GlobalConfig
from util.log_util import TempLog
from util.path_util import get_record_root, safe_join, ensure_dir_exists


@dataclass
class ScreenshotRecordResult:
    """
    输出文件信息：
    - output_path: 最终落盘路径（zip）
    - output_name: 文件名
    - shots_dir: 截图目录（便于排查）
    - shots: 截图文件名列表（zip 内同名）
    """

    output_path: str
    output_name: str
    shots_dir: str
    shots: List[str]


class ScreenshotRecorder:
    """
    每隔 interval_sec 采集一张截图，任务结束时打包成 record/<task_id>.zip。
    使用 adb exec-out screencap -p，兼容性比 uiautomator 截图更高。
    """

    def __init__(
        self,
        task_id: str,
        device_id: str,
        logger: Optional[TempLog] = None,
        interval_sec: float = 1.0,
    ) -> None:
        self.task_id = task_id
        self.device_id = device_id
        self.log = logger or TempLog()
        self.interval_sec = max(float(interval_sec or 1.0), 0.2)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[ScreenshotRecordResult] = None
        self._shots_dir: Optional[str] = None
        self._shots: List[str] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self, wait: bool = True, timeout: float = 10.0) -> Optional[ScreenshotRecordResult]:
        self._stop_event.set()
        if wait and self._thread:
            self._thread.join(timeout=timeout)
        return self._result

    @property
    def result(self) -> Optional[ScreenshotRecordResult]:
        return self._result

    def _run_loop(self) -> None:
        try:
            record_root = get_record_root()
            ensure_dir_exists(record_root)
            shots_dir = safe_join(record_root, f"{self.task_id}_shots")
            ensure_dir_exists(shots_dir)
            self._shots_dir = shots_dir

            adb = GlobalConfig["device"]["adb_path"]
            idx = 1
            next_t = time.time()

            self.log.warning(
                f"录屏不可用，已降级为截图模式：每{self.interval_sec:.1f}s保存一张（task={self.task_id}）"
            )

            while not self._stop_event.is_set():
                now = time.time()
                # 简单节流：对齐到 interval，避免堆积
                if now < next_t:
                    time.sleep(min(0.2, next_t - now))
                    continue

                name = f"{idx:06d}.png"
                out_path = safe_join(shots_dir, name)

                ok = self._capture_png(adb, out_path)
                if ok:
                    self._shots.append(name)
                    idx += 1
                else:
                    # 连续失败不要疯狂刷；下一轮继续尝试即可
                    time.sleep(0.5)

                next_t = max(next_t + self.interval_sec, time.time())

            self._result = self._finalize_zip(record_root, shots_dir)
        except Exception as e:
            try:
                self.log.error(f"截图录制线程异常退出：{e}", exc_info=True)
            except Exception:
                pass

    def _capture_png(self, adb: str, out_path: str) -> bool:
        """
        采集一张 png。优先 exec-out（直接回传），失败时尝试 shell + cat。
        """
        try:
            r = subprocess.run(
                [adb, "-s", self.device_id, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=12,
            )
            if r.returncode == 0 and r.stdout and len(r.stdout) > 2000:
                with open(out_path, "wb") as f:
                    f.write(r.stdout)
                return True
        except Exception:
            pass

        # 兜底：某些环境 exec-out 不稳定，尝试 shell 输出
        try:
            r = subprocess.run(
                [adb, "-s", self.device_id, "shell", "screencap", "-p"],
                capture_output=True,
                timeout=12,
            )
            if r.returncode == 0 and r.stdout and len(r.stdout) > 2000:
                with open(out_path, "wb") as f:
                    f.write(r.stdout)
                return True
        except Exception:
            pass

        try:
            self.log.debug(f"截图失败：device={self.device_id}, out={out_path}")
        except Exception:
            pass
        return False

    def _finalize_zip(self, record_root: str, shots_dir: str) -> Optional[ScreenshotRecordResult]:
        if not self._shots:
            return None

        final_name = f"{self.task_id}.zip"
        final_path = safe_join(record_root, final_name)
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
        except Exception:
            pass

        try:
            with zipfile.ZipFile(final_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name in self._shots:
                    p = safe_join(shots_dir, name)
                    if os.path.exists(p) and os.path.getsize(p) > 1024:
                        zf.write(p, arcname=name)

            if os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
                return ScreenshotRecordResult(
                    output_path=final_path,
                    output_name=final_name,
                    shots_dir=shots_dir,
                    shots=list(self._shots),
                )
        except Exception as e:
            self.log.error(f"截图打包 zip 失败：{e}", exc_info=True)
            return None

        return None

