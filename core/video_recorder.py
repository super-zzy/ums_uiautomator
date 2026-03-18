# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import socket
import struct
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
class VideoRecordResult:
    """
    输出文件信息：
    - output_path: 最终落盘路径（mp4 或 zip）
    - output_name: 文件名（用于下载时的 attachment 名称）
    - segments: 原始分段文件列表（若发生分段）
    """

    output_path: str
    output_name: str
    segments: List[str]


class VideoRecorder:
    """
    全程录制器（优先 minicap 方案）。

    当前策略（按优先级尝试）：
    1) minicap（设备端抓帧） + ffmpeg（主机侧编码 mp4）
    2) adb shell screenrecord（设备端落盘 + pull，分段规避时长限制）
    3) scrcpy（主机侧录屏，作为兜底）

    说明：
    - minicap 需要设备端存在 `minicap` 与 `minicap.so`，且主机侧需要 ffmpeg 才能编码输出 mp4。
    - 若 minicap 不可用，会自动回退到旧方案，避免影响测试任务本身。
    """

    def __init__(
        self,
        task_id: str,
        device_id: str,
        logger: Optional[TempLog] = None,
        time_limit_sec: int = 180,
    ) -> None:
        self.task_id = task_id
        self.device_id = device_id
        self.log = logger or TempLog()
        self.time_limit_sec = max(int(time_limit_sec or 180), 10)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started_ok = threading.Event()
        self._current_proc: Optional[subprocess.Popen] = None
        self._current_remote_path: Optional[str] = None
        self._remote_dir: Optional[str] = None
        self._remote_segments: List[str] = []
        self._segments: List[str] = []
        self._result: Optional[VideoRecordResult] = None
        self._backend: str = "unknown"  # minicap | adb_screenrecord | scrcpy | unknown
        self._screenrecord_path: Optional[str] = None
        self._minicap_remote_dir: str = "/data/local/tmp"
        self._minicap_bin: str = "/data/local/tmp/minicap"
        self._minicap_so: str = "/data/local/tmp/minicap.so"
        self._minicap_port: int = 1717
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._minicap_sock: Optional[socket.socket] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._started_ok.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self, wait: bool = True, timeout: float = 15.0) -> Optional[VideoRecordResult]:
        self._stop_event.set()
        # 优先尝试停止 minicap/screenrecord，让其有机会落盘/flush
        try:
            self._stop_remote_minicap()
            self._stop_remote_screenrecord()
        except Exception:
            pass

        # 再尝试终止本地进程，避免阻塞
        try:
            if self._current_proc and self._current_proc.poll() is None:
                self._current_proc.terminate()
        except Exception:
            pass
        try:
            if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
                # 关闭 stdin 触发 ffmpeg 正常收尾
                try:
                    if self._ffmpeg_proc.stdin:
                        self._ffmpeg_proc.stdin.close()
                except Exception:
                    pass
                self._ffmpeg_proc.terminate()
        except Exception:
            pass
        try:
            if self._minicap_sock:
                try:
                    self._minicap_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self._minicap_sock.close()
        except Exception:
            pass

        if wait and self._thread:
            self._thread.join(timeout=timeout)
        return self._result

    def wait_started(self, timeout: float = 3.0) -> bool:
        """
        等待录屏后端真正启动成功（而不是线程启动成功）。
        用于在 screenrecord/minicap/scrcpy 秒退时快速感知并降级。
        """
        try:
            return bool(self._started_ok.wait(timeout=max(float(timeout or 0), 0.0)))
        except Exception:
            return False

    def can_record(self) -> bool:
        """
        同步探测：当前环境是否存在“可用的录屏后端”。

        用途：在启动测试任务前快速判断，避免 UI 勾选了“全程录制视频”但实际无任何方案可用时，
        录屏线程启动后静默退出，导致用户以为“在录屏但没产物”。
        """
        try:
            # 1) minicap + ffmpeg
            if self._ensure_minicap_ready() and shutil.which("ffmpeg"):
                return True
        except Exception:
            pass

        # 2) adb screenrecord
        try:
            if self._detect_screenrecord_path():
                return True
        except Exception:
            pass

        # 3) scrcpy
        try:
            if shutil.which("scrcpy"):
                return True
        except Exception:
            pass

        return False

    @property
    def result(self) -> Optional[VideoRecordResult]:
        return self._result

    def _run_loop(self) -> None:
        try:
            record_root = get_record_root()
            ensure_dir_exists(record_root)

            adb = GlobalConfig["device"]["adb_path"]

            # 1) 优先 minicap（需要 ffmpeg）
            try:
                if self._ensure_minicap_ready() and shutil.which("ffmpeg"):
                    self._backend = "minicap"
                    self.log.info("将使用 minicap + ffmpeg 方案进行全程录屏")
                    self._result = self._run_minicap_record(record_root)
                    return
                if not shutil.which("ffmpeg"):
                    self.log.warning("未检测到 ffmpeg，minicap 方案无法输出 mp4，将回退到旧方案")
            except Exception as e:
                self.log.warning(f"minicap 方案初始化失败，将回退旧方案：{e}")

            # 2) 旧方案：screenrecord 分段
            self._screenrecord_path = self._detect_screenrecord_path()
            if not self._screenrecord_path:
                self.log.warning("设备端 screenrecord 不可用，将尝试 scrcpy 兜底录屏")
                scrcpy = shutil.which("scrcpy")
                if scrcpy:
                    self._backend = "scrcpy"
                    self._result = self._run_scrcpy_record(record_root, scrcpy)
                    return
                self.log.error(
                    "minicap 不可用、screenrecord 不可用，且主机未安装 scrcpy，无法录屏。"
                    "建议：安装 ffmpeg + minicap，或确保设备包含 screenrecord，或安装 scrcpy。"
                )
                return
            self.log.info(f"screenrecord 路径：{self._screenrecord_path}")
            self._backend = "adb_screenrecord"

            # 选择设备端可写目录：录屏先暂存设备端，任务结束再统一 pull
            self._remote_dir = self._select_remote_dir()
            if not self._remote_dir:
                self.log.error("未找到可写的设备端目录，无法录屏")
                return
            self.log.info(f"录屏临时目录：{self._remote_dir}")

            seg_idx = 1
            while not self._stop_event.is_set():
                remote_name = f"ums_record_{self.task_id}_{seg_idx}.mp4"
                remote_path = f"{self._remote_dir.rstrip('/')}/{remote_name}"
                self._current_remote_path = remote_path

                # 先用带 bit-rate 的命令；若不兼容则自动回退到更通用的参数组合
                cmd_primary = [
                    adb,
                    "-s",
                    self.device_id,
                    "shell",
                    self._screenrecord_path or "screenrecord",
                    "--bit-rate",
                    "8000000",
                    "--time-limit",
                    str(self.time_limit_sec),
                    remote_path,
                ]
                cmd_fallback = [
                    adb,
                    "-s",
                    self.device_id,
                    "shell",
                    self._screenrecord_path or "screenrecord",
                    "--time-limit",
                    str(self.time_limit_sec),
                    remote_path,
                ]

                self.log.info(
                    f"开始录屏分段：task={self.task_id}, device={self.device_id}, seg={seg_idx}, limit={self.time_limit_sec}s"
                )
                # 尝试启动录屏（若瞬时失败，则回退参数）
                self._current_proc = None
                used_fallback = False
                for attempt, cmd in enumerate((cmd_primary, cmd_fallback), start=1):
                    try:
                        self._current_proc = subprocess.Popen(
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                        )
                    except Exception as e:
                        self.log.error(f"启动 screenrecord 失败：{e}", exc_info=True)
                        self._current_proc = None
                        break

                    # 若 0.8s 内就退出，通常是参数不兼容/命令不可用；尝试 fallback
                    time.sleep(0.8)
                    if self._current_proc.poll() is None:
                        # 进程在短时间内存活，认为后端已启动
                        self._started_ok.set()
                        used_fallback = attempt == 2
                        break

                    # 读取快速失败原因
                    try:
                        out_b, err_b = self._current_proc.communicate(timeout=1.0)
                    except Exception:
                        out_b, err_b = b"", b""
                    out_s = (out_b or b"").decode("utf-8", errors="ignore").strip()
                    err_s = (err_b or b"").decode("utf-8", errors="ignore").strip()
                    self.log.warning(
                        f"screenrecord 启动后快速退出（seg={seg_idx}, attempt={attempt}），"
                        f"stdout={out_s[:200]}, stderr={err_s[:200]}"
                    )
                    self._current_proc = None
                    if attempt == 2:
                        break

                if not self._current_proc:
                    # 两种参数都失败
                    self.log.error(f"任务{self.task_id}录屏启动失败，停止录屏线程")
                    break
                if used_fallback:
                    self.log.info(f"seg={seg_idx} 使用 fallback 参数启动 screenrecord")

                # 等待该分段结束（超时/用户 stop / 录制完成）
                while True:
                    if self._stop_event.is_set():
                        # stop 时：优先停设备端 screenrecord，避免 remote 文件不存在
                        try:
                            self._stop_remote_screenrecord()
                        except Exception:
                            pass
                        break
                    if not self._current_proc:
                        break
                    rc = self._current_proc.poll()
                    if rc is not None:
                        break
                    time.sleep(0.3)

                # 分段结束后，若命令返回非 0，输出 stderr 便于排查（不要因为解码问题崩线程）
                try:
                    if self._current_proc:
                        rc = self._current_proc.poll()
                        if rc is not None and rc != 0:
                            out_b, err_b = self._current_proc.communicate(timeout=1.0)
                            out_s = (out_b or b"").decode("utf-8", errors="ignore").strip()
                            err_s = (err_b or b"").decode("utf-8", errors="ignore").strip()
                            self.log.warning(
                                f"screenrecord 退出异常：seg={seg_idx}, rc={rc}, stdout={out_s[:200]}, stderr={err_s[:200]}"
                            )
                except Exception:
                    pass

                # 分段文件暂存在设备端，等待任务结束统一 pull（减少录制过程中 pull 失败干扰）
                try:
                    # stop 场景下，screenrecord 需要更多时间 flush 到文件系统
                    wait_sec = 8.0 if self._stop_event.is_set() else 3.0
                    remote_ok = self._wait_remote_file(remote_path, max_wait_sec=wait_sec)
                    if remote_ok:
                        self._remote_segments.append(remote_path)
                        self.log.info(f"录屏分段已暂存：{remote_path}")
                    else:
                        if self._stop_event.is_set():
                            self.log.info(f"录屏最后分段未落盘，跳过：task={self.task_id}, seg={seg_idx}")
                        else:
                            self.log.warning(f"录屏分段未生成，跳过：seg={seg_idx}, path={remote_path}")
                except Exception as e:
                    self.log.error(f"检查设备端录屏分段失败：{e}", exc_info=True)

                seg_idx += 1

                # 若是因为 stop 触发的退出，就不继续下一段
                if self._stop_event.is_set():
                    break

            self._current_proc = None
            self._current_remote_path = None
            self._result = self._pull_and_finalize(record_root)
        except Exception as e:
            # 避免录屏线程静默退出，必须把异常打到日志里
            try:
                self.log.error(f"录屏线程异常退出：{e}", exc_info=True)
            except Exception:
                pass

    def _ensure_minicap_ready(self) -> bool:
        """
        判断设备端 minicap 是否可用。
        这里不做自动下载（避免引入二进制依赖），只做“存在性 + 可执行性”检测。
        """
        try:
            if self._is_remote_executable(self._minicap_bin) and self._remote_file_exists(self._minicap_so):
                return True
        except Exception:
            return False
        return False

    def _get_wm_size(self) -> Optional[tuple[int, int]]:
        """
        获取设备当前分辨率，优先 `wm size`，失败则回退 dumpsys。
        """
        try:
            r = self._adb_shell("wm", "size", timeout=8.0)
            s = (r.stdout or "").strip()
            # Physical size: 1080x2400
            for line in s.splitlines():
                if "Physical size" in line and "x" in line:
                    part = line.split(":")[-1].strip()
                    w_s, h_s = part.split("x", 1)
                    return int(w_s.strip()), int(h_s.strip())
        except Exception:
            pass
        try:
            r = self._adb_shell("sh", "-c", "dumpsys display | grep -m 1 -E 'mDisplayInfo|DisplayInfo' 2>/dev/null", timeout=10.0)
            s = (r.stdout or "").strip()
            # 兼容性兜底：用正则更稳，但这里保持轻量，尽最大努力解析 WxH
            import re

            m = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", s)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        return None

    def _adb_forward(self, local_port: int, abstract_name: str) -> bool:
        adb = GlobalConfig["device"]["adb_path"]
        try:
            r = subprocess.run(
                [adb, "-s", self.device_id, "forward", f"tcp:{local_port}", f"localabstract:{abstract_name}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=8,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _adb_forward_remove(self, local_port: int) -> None:
        adb = GlobalConfig["device"]["adb_path"]
        try:
            subprocess.run(
                [adb, "-s", self.device_id, "forward", "--remove", f"tcp:{local_port}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=6,
            )
        except Exception:
            pass

    def _stop_remote_minicap(self) -> None:
        """
        通过设备端信号停止 minicap。
        """
        for cmd in (
            ["pkill", "-2", "minicap"],
            ["killall", "-2", "minicap"],
            ["pkill", "minicap"],
        ):
            try:
                self._adb_shell(*cmd, timeout=5.0)
                return
            except Exception:
                continue

    def _run_minicap_record(self, record_root: str) -> Optional[VideoRecordResult]:
        """
        minicap + ffmpeg：录制输出单文件 mp4（record_root/<task_id>.mp4）
        """
        ensure_dir_exists(record_root)
        final_name = f"{self.task_id}.mp4"
        final_path = safe_join(record_root, final_name)
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
        except Exception:
            pass

        size = self._get_wm_size()
        if not size:
            self.log.warning("无法获取设备分辨率，minicap 录屏启动失败，将回退旧方案")
            return None
        w, h = size
        proj = f"{w}x{h}@{w}x{h}/0"

        # 1) 启动 minicap（监听 localabstract:minicap）
        # -S: 以 socket server 方式输出
        # -P: 投影参数
        # -Q: JPEG 质量（1-100）
        cmd = [
            GlobalConfig["device"]["adb_path"],
            "-s",
            self.device_id,
            "shell",
            "sh",
            "-c",
            f"LD_LIBRARY_PATH={self._minicap_remote_dir} {self._minicap_bin} -P {proj} -S -Q 80",
        ]
        self.log.info(f"minicap 启动：{' '.join(cmd)}")
        try:
            self._current_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            self.log.warning(f"启动 minicap 失败：{e}")
            return None

        # 2) 建立 adb forward，并连接本地 socket 读取帧
        self._adb_forward_remove(self._minicap_port)
        if not self._adb_forward(self._minicap_port, "minicap"):
            self.log.warning("adb forward 到 minicap 失败")
            self._stop_remote_minicap()
            return None

        # 3) 启动 ffmpeg（从 stdin 接收连续 JPEG，编码为 mp4）
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.log.warning("未找到 ffmpeg，无法编码输出 mp4")
            self._stop_remote_minicap()
            return None

        ffmpeg_cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "mjpeg",
            "-r",
            "10",
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            final_path,
        ]
        try:
            self._ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except Exception as e:
            self.log.warning(f"启动 ffmpeg 失败：{e}")
            self._stop_remote_minicap()
            return None

        # 4) 读取 minicap 帧并写入 ffmpeg stdin
        try:
            s = socket.create_connection(("127.0.0.1", self._minicap_port), timeout=8.0)
            self._minicap_sock = s
            s.settimeout(2.0)

            # 全局 header（24 bytes；header_size 字段允许扩展，这里按协议读取）
            global_header = self._recv_exact(s, 2)
            version = global_header[0]
            header_size = global_header[1]
            rest = self._recv_exact(s, max(0, header_size - 2))
            _ = version, rest  # 仅用于占位，避免未使用变量警告

            # 能读到 header 说明 minicap 拉流链路已建立
            self._started_ok.set()

            last_write = time.time()
            while not self._stop_event.is_set():
                # 每帧：4 bytes little endian length + jpeg payload
                len_b = self._recv_exact(s, 4)
                frame_len = struct.unpack("<I", len_b)[0]
                if frame_len <= 0 or frame_len > 20_000_000:
                    # 防御：异常长度直接跳出
                    self.log.warning(f"minicap 帧长度异常：{frame_len}")
                    break
                jpg = self._recv_exact(s, frame_len)
                if not jpg:
                    break
                if self._ffmpeg_proc and self._ffmpeg_proc.stdin:
                    try:
                        self._ffmpeg_proc.stdin.write(jpg)
                        self._ffmpeg_proc.stdin.flush()
                        last_write = time.time()
                    except Exception:
                        break

                # 若 minicap 进程异常退出，也要退出循环
                if self._current_proc and self._current_proc.poll() is not None:
                    break

                # 若长时间无写入（例如 socket 卡住），避免无限阻塞
                if time.time() - last_write > 10:
                    self.log.warning("minicap 长时间无帧输出，结束录制")
                    break
        except Exception as e:
            self.log.warning(f"minicap 拉流异常：{e}")
        finally:
            # stop：清理
            try:
                if self._ffmpeg_proc and self._ffmpeg_proc.stdin:
                    try:
                        self._ffmpeg_proc.stdin.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if self._ffmpeg_proc:
                    self._ffmpeg_proc.wait(timeout=8)
            except Exception:
                try:
                    if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
                        self._ffmpeg_proc.terminate()
                except Exception:
                    pass
            self._ffmpeg_proc = None

            try:
                if self._minicap_sock:
                    try:
                        self._minicap_sock.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._minicap_sock = None

            try:
                self._stop_remote_minicap()
            except Exception:
                pass
            self._adb_forward_remove(self._minicap_port)

        # 5) 检查输出文件
        try:
            if os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
                return VideoRecordResult(output_path=final_path, output_name=final_name, segments=[])
        except Exception:
            pass
        self.log.warning("minicap 录屏文件未生成或过小")
        return None

    def _recv_exact(self, s: socket.socket, n: int) -> bytes:
        """
        从 socket 读取恰好 n 字节（或抛异常）。
        """
        buf = bytearray()
        while len(buf) < n and not self._stop_event.is_set():
            chunk = s.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        if len(buf) != n:
            raise RuntimeError(f"socket read short: need={n}, got={len(buf)}")
        return bytes(buf)

    def _detect_screenrecord_path(self) -> Optional[str]:
        """
        在设备端探测 screenrecord 可执行文件路径。
        注意：部分设备没有 `which`，这里优先用 `command -v`，再尝试常见路径。
        返回可执行路径（如 /system/bin/screenrecord），否则 None。
        """
        adb = GlobalConfig["device"]["adb_path"]

        def _trim(s: str) -> str:
            return (s or "").strip()

        # 1) command -v（兼容性比 which 更好）
        try:
            r = subprocess.run(
                [adb, "-s", self.device_id, "shell", "sh", "-c", "command -v screenrecord 2>/dev/null"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=8,
            )
            p = _trim(r.stdout)
            if p and r.returncode == 0:
                # 再验证可执行性
                if self._is_remote_executable(p):
                    return p
        except Exception as e:
            self.log.debug(f"command -v screenrecord 探测异常（忽略）：{e}")

        # 2) 常见路径探测（华为/鸿蒙/定制 ROM 可能不在 PATH 或存在但不可执行）
        common_paths = [
            "/system/bin/screenrecord",
            "/system/xbin/screenrecord",
            "/vendor/bin/screenrecord",
            "/product/bin/screenrecord",
            "/system_ext/bin/screenrecord",
        ]
        for p in common_paths:
            try:
                if self._is_remote_executable(p):
                    return p
            except Exception:
                continue

        # 3) 输出诊断信息（便于排查“inaccessible or not found”是不存在还是权限/SELinux）
        try:
            diag = subprocess.run(
                [
                    adb,
                    "-s",
                    self.device_id,
                    "shell",
                    "sh",
                    "-c",
                    "ls -l /system/bin/screenrecord 2>&1; id 2>&1; getenforce 2>&1",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=8,
            )
            self.log.warning(
                "screenrecord 探测失败诊断："
                f"stdout={(diag.stdout or '').strip()[:400]}, stderr={(diag.stderr or '').strip()[:200]}"
            )
        except Exception:
            pass

        return None

    def _is_remote_executable(self, remote_path: str) -> bool:
        """
        判断设备端文件是否存在且可执行。
        """
        r = self._adb_shell("sh", "-c", f"test -x \"{remote_path}\" && echo OK || echo NO", timeout=6.0)
        return (r.stdout or "").strip().endswith("OK")

    def _run_scrcpy_record(self, record_root: str, scrcpy_path: str) -> Optional[VideoRecordResult]:
        """
        使用 scrcpy 在主机侧录屏（不依赖设备端 screenrecord）。
        - 录制文件直接生成在本地 record_root/<task_id>.mp4
        """
        ensure_dir_exists(record_root)
        final_name = f"{self.task_id}.mp4"
        final_path = safe_join(record_root, final_name)
        # 覆盖旧文件
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
        except Exception:
            pass

        # scrcpy 录制。常用参数：
        # --no-playback: 不在本机播放音频（减少依赖）
        # --turn-screen-off: 可选，这里不强制
        cmd = [
            scrcpy_path,
            "--serial",
            self.device_id,
            "--record",
            final_path,
            "--no-playback",
        ]
        self.log.info(f"scrcpy 开始录屏：{' '.join(cmd)}")
        try:
            self._current_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            self.log.error(f"启动 scrcpy 失败：{e}", exc_info=True)
            return None

        # 给进程一点时间，确认不是秒退
        time.sleep(0.6)
        try:
            if self._current_proc and self._current_proc.poll() is None:
                self._started_ok.set()
        except Exception:
            pass

        # 等待 stop 信号
        while not self._stop_event.is_set():
            if not self._current_proc:
                break
            rc = self._current_proc.poll()
            if rc is not None:
                # 进程异常退出，输出 stderr
                try:
                    out_b, err_b = self._current_proc.communicate(timeout=1.0)
                    out_s = (out_b or b"").decode("utf-8", errors="ignore").strip()
                    err_s = (err_b or b"").decode("utf-8", errors="ignore").strip()
                    self.log.warning(f"scrcpy 提前退出：rc={rc}, stdout={out_s[:200]}, stderr={err_s[:200]}")
                except Exception:
                    pass
                break
            time.sleep(0.3)

        # stop：终止 scrcpy
        try:
            if self._current_proc and self._current_proc.poll() is None:
                self._current_proc.terminate()
        except Exception:
            pass

        # 给文件系统一点时间 flush
        time.sleep(0.6)
        self._current_proc = None

        if os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
            return VideoRecordResult(output_path=final_path, output_name=final_name, segments=[])
        self.log.warning("scrcpy 录屏文件未生成或过小")
        return None

    def _adb_shell(self, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess:
        adb = GlobalConfig["device"]["adb_path"]
        cmd = [adb, "-s", self.device_id, "shell", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )

    def _stop_remote_screenrecord(self) -> None:
        """
        通过设备端信号停止 screenrecord（优先 SIGINT），提升 remote 文件落盘成功率。
        """
        # 优先 -2(SIGINT)；失败则 fallback killall/pkill
        for cmd in (
            ["pkill", "-2", "screenrecord"],
            ["killall", "-2", "screenrecord"],
            ["pkill", "screenrecord"],
        ):
            try:
                self._adb_shell(*cmd, timeout=5.0)
                return
            except Exception:
                continue

    def _remote_file_exists(self, remote_path: str) -> bool:
        try:
            r = self._adb_shell("ls", "-l", remote_path, timeout=5.0)
            return r.returncode == 0 and ("No such file" not in (r.stderr or ""))
        except Exception:
            return False

    def _wait_remote_file(self, remote_path: str, max_wait_sec: float = 3.0) -> bool:
        end = time.time() + max(0.0, max_wait_sec)
        while time.time() < end:
            if self._remote_file_exists(remote_path):
                return True
            time.sleep(0.2)
        ok = self._remote_file_exists(remote_path)
        if not ok:
            # 关键排查信息：文件不存在时把父目录简单列一下（避免静默失败）
            try:
                parent = remote_path.rsplit("/", 1)[0] if "/" in remote_path else remote_path
                r = self._adb_shell("ls", "-l", parent, timeout=6.0)
                self.log.debug(
                    f"等待录屏文件落盘超时：path={remote_path}, parent_ls_rc={r.returncode}, "
                    f"stdout={(r.stdout or '').strip()[:300]}, stderr={(r.stderr or '').strip()[:300]}"
                )
            except Exception:
                pass
        return ok

    def _select_remote_dir(self) -> Optional[str]:
        """
        选择设备端可写目录，用于暂存录屏文件，任务结束再 pull。
        通过 echo>file + rm 验证写权限，避免“路径存在但不可写”。
        """
        # 经验优先级：
        # - 公共媒体目录（Movies/Download/DCIM）在多数机型上对 `screenrecord` 更稳定
        # - 但部分设备/ROM 的 shell 可能缺少 `mkdir -p`/`which` 等常用命令
        #   因此这里采用“可创建子目录则用子目录；否则退回到已存在父目录”的策略，
        #   保证在 mkdir 不可用时也尽量能录屏。
        base_candidates = [
            "/sdcard/Movies",
            "/sdcard/Download",
            "/sdcard/DCIM",
            "/sdcard/UMS",
            "/storage/emulated/0/Movies",
            "/storage/emulated/0/Download",
            "/storage/self/primary/Movies",
            "/sdcard",
            "/storage/emulated/0",
            "/storage/self/primary",
            "/data/local/tmp",
        ]
        ts = int(time.time() * 1000)
        for parent in base_candidates:
            parent = parent.rstrip("/")
            # 优先使用专用子目录（若能创建）
            preferred = f"{parent}/UMSRecord"
            # 也允许直接落在 parent（当 mkdir 不可用/不可写时）
            for base in (preferred, parent):
                base = base.rstrip("/")
                test_file = f"{base}/.ums_record_probe_{ts}.tmp"
            try:
                # 华为/鸿蒙等设备上，shell 内置工具可能缺失或行为不同：
                # - 统一用双引号包裹路径（避免单引号解析差异）
                # - rm 使用 `--`，防止路径以 '-' 开头被当作参数
                # - mkdir 尽最大努力，但不因失败直接退出（仍尝试直接写入已存在目录）
                script_mkdir = (
                    f"mkdir -p \"{base}\" "
                    f"|| toybox mkdir -p \"{base}\" "
                    f"|| toolbox mkdir -p \"{base}\" "
                    f"|| busybox mkdir -p \"{base}\" "
                    f"|| true"
                )
                try:
                    r_mkdir = self._adb_shell("sh", "-c", script_mkdir, timeout=8.0)
                    if r_mkdir.returncode != 0:
                        self.log.debug(
                            f"mkdir 尝试失败（可能命令缺失或无权限）：dir={base}, rc={r_mkdir.returncode}, "
                            f"stdout={(r_mkdir.stdout or '').strip()[:200]}, stderr={(r_mkdir.stderr or '').strip()[:200]}"
                        )
                except Exception as e:
                    self.log.debug(f"mkdir 尝试异常（忽略）：dir={base}, err={e}")

                r1 = self._adb_shell("sh", "-c", f"echo ok > \"{test_file}\"", timeout=6.0)
                if r1.returncode != 0:
                    self.log.debug(
                        f"录屏目录探测写入失败：dir={base}, rc={r1.returncode}, "
                        f"stderr={(r1.stderr or '').strip()[:200]}"
                    )
                    continue
                # rm 在部分设备上对 -f/参数解析兼容性较差，这里加 `--` 并保留 stdout/stderr
                r2 = self._adb_shell("sh", "-c", f"rm -f -- \"{test_file}\"", timeout=6.0)
                if r2.returncode != 0:
                    self.log.debug(
                        f"录屏目录探测删除失败：dir={base}, rc={r2.returncode}, "
                        f"stdout={(r2.stdout or '').strip()[:200]}, stderr={(r2.stderr or '').strip()[:200]}"
                    )
                    # 对“可写目录”的判定应以“能创建文件”为准：
                    # 某些设备/ROM 的 rm 行为异常会导致清理失败，但并不代表目录不可写。
                    self.log.warning(
                        f"录屏目录可写但清理探测文件失败（忽略）：dir={base}, file={test_file}"
                    )
                return base
            except Exception as e:
                self.log.debug(f"录屏目录探测异常：dir={base}, err={e}")
                continue
        return None

    def _pull_and_finalize(self, record_root: str) -> Optional[VideoRecordResult]:
        """
        任务结束后统一 pull 设备端分段到本地，再走合并/打包逻辑。
        """
        adb = GlobalConfig["device"]["adb_path"]
        if not self._remote_segments:
            return None

        # pull
        for idx, remote_path in enumerate(self._remote_segments, start=1):
            local_seg_name = f"{self.task_id}_{idx:03d}.mp4"
            local_seg_path = safe_join(record_root, local_seg_name)
            try:
                pull = subprocess.run(
                    [adb, "-s", self.device_id, "pull", remote_path, local_seg_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                )
                if (
                    pull.returncode == 0
                    and os.path.exists(local_seg_path)
                    and os.path.getsize(local_seg_path) > 1024
                ):
                    self._segments.append(local_seg_path)
                else:
                    if os.path.exists(local_seg_path):
                        try:
                            os.remove(local_seg_path)
                        except Exception:
                            pass
                    self.log.warning(
                        f"pull 录屏分段失败或文件过小：idx={idx}, remote={remote_path}, "
                        f"stderr={(pull.stderr or '').strip()[:200]}"
                    )
            except Exception as e:
                self.log.error(f"pull 录屏分段异常：remote={remote_path}, err={e}", exc_info=True)

        # 清理设备端临时文件
        for remote_path in self._remote_segments:
            try:
                subprocess.run(
                    [adb, "-s", self.device_id, "shell", "rm", "-f", remote_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=10,
                )
            except Exception:
                pass

        return self._finalize(record_root)

    def _finalize(self, record_root: str) -> Optional[VideoRecordResult]:
        if not self._segments:
            return None

        # 单段：直接重命名为 task_id.mp4
        if len(self._segments) == 1:
            final_name = f"{self.task_id}.mp4"
            final_path = safe_join(record_root, final_name)
            try:
                # 覆盖旧文件
                if os.path.exists(final_path):
                    os.remove(final_path)
                shutil.move(self._segments[0], final_path)
                return VideoRecordResult(
                    output_path=final_path,
                    output_name=final_name,
                    segments=[],
                )
            except Exception as e:
                self.log.error(f"保存最终录屏失败：{e}", exc_info=True)
                return None

        # 多段：优先 ffmpeg 合并，否则打包 zip
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                list_path = safe_join(record_root, f"{self.task_id}_concat.txt")
                with open(list_path, "w", encoding="utf-8") as f:
                    for p in self._segments:
                        # ffmpeg concat demuxer 需要 file 'path'
                        p2 = p.replace("\\", "/")
                        f.write(f"file '{p2}'\n")

                final_name = f"{self.task_id}.mp4"
                final_path = safe_join(record_root, final_name)
                if os.path.exists(final_path):
                    os.remove(final_path)

                cmd = [
                    ffmpeg,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_path,
                    "-c",
                    "copy",
                    final_path,
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
                if r.returncode == 0 and os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
                    # 合并成功，清理分段与列表文件
                    try:
                        os.remove(list_path)
                    except Exception:
                        pass
                    for p in self._segments:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                    return VideoRecordResult(
                        output_path=final_path,
                        output_name=final_name,
                        segments=[],
                    )
                self.log.warning(f"ffmpeg 合并失败，将回退 zip：{(r.stderr or '')[:200]}")
            except Exception as e:
                self.log.warning(f"ffmpeg 合并异常，将回退 zip：{e}")

        # zip
        try:
            final_name = f"{self.task_id}.zip"
            final_path = safe_join(record_root, final_name)
            if os.path.exists(final_path):
                os.remove(final_path)
            with zipfile.ZipFile(final_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in self._segments:
                    arc = os.path.basename(p)
                    zf.write(p, arcname=arc)
            # 这里保留分段文件，便于排查；如需清理可改为删除
            return VideoRecordResult(
                output_path=final_path,
                output_name=final_name,
                segments=[os.path.basename(p) for p in self._segments],
            )
        except Exception as e:
            self.log.error(f"打包录屏 zip 失败：{e}", exc_info=True)
            return None

