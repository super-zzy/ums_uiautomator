# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
import subprocess
import shutil
import time
import json
from datetime import datetime
from typing import Tuple, Dict, Optional
from util.log_util import LogUtil, TempLog
from util.path_util import safe_join, ensure_dir_exists, get_file_size
from conf import GlobalConfig


class TestExecutor:
    def __init__(self, task_id: str, device_id: str, suite_abs_path: str):
        self.task_id = task_id
        self.device_id = device_id
        self.suite_abs_path = suite_abs_path
        self.log = LogUtil(
            device_id=device_id, task_id=task_id, logger_name=f"task_{task_id}"
        )

        # 初始化路径（基于配置的报告根目录）
        self.report_root = GlobalConfig["path"]["report_root_dir"]
        self.task_report_dir = safe_join(self.report_root, self.task_id)
        self.allure_raw_dir = safe_join(self.task_report_dir, "allure_raw")
        self.allure_html_dir = safe_join(self.task_report_dir, "allure_html")
        self.task_log_path = safe_join(self.task_report_dir, f"task_{task_id}.log")
        self.report_meta_path = safe_join(self.task_report_dir, "report_meta.json")
        self.allure_log_path = safe_join(self.task_report_dir, "allure_generate.log")

        # 报告生成配置
        self.allure_config = {
            "clean_before_generate": GlobalConfig["test"]["allure_clean"],
            "generate_timeout": GlobalConfig["test"].get("allure_generate_timeout", 300),
            "report_compress": GlobalConfig["test"].get("report_compress", False),
            "compress_format": GlobalConfig["test"].get("report_compress_format", "zip"),
            "keep_raw_data": GlobalConfig["test"].get("keep_allure_raw", True)
        }

    def prepare(self) -> None:
        """准备测试环境（清理旧目录、创建新目录）"""
        self.log.info(f"准备测试环境：{self.task_report_dir}")

        # 清理旧报告
        if os.path.exists(self.task_report_dir):
            old_dir_size = get_file_size(self.task_report_dir)
            self.log.warning(
                f"清理旧报告目录：{self.task_report_dir}（预估大小：{old_dir_size:.2f}MB）"
            )
            shutil.rmtree(self.task_report_dir)

        # 创建新目录
        dirs_to_create = [self.allure_raw_dir, self.allure_html_dir]
        for dir_path in dirs_to_create:
            ensure_dir_exists(dir_path)
            self.log.debug(f"创建目录成功：{dir_path}")

        self.log.info(f"测试目录初始化完成：{self.task_report_dir}")

        # 校验用例路径
        if not os.path.exists(self.suite_abs_path):
            raise FileNotFoundError(f"测试用例不存在：{self.suite_abs_path}")
        if not os.path.isfile(self.suite_abs_path):
            raise ValueError(f"{self.suite_abs_path}不是有效文件")
        if not os.access(self.suite_abs_path, os.R_OK):
            raise PermissionError(f"无读取权限：{self.suite_abs_path}")
        self.log.info(
            f"测试用例校验通过：{self.suite_abs_path}（文件大小：{get_file_size(self.suite_abs_path):.2f}KB）"
        )

    def run_pytest(self) -> Tuple[int, str, str]:
        """执行Pytest测试（生成Allure原始报告）"""
        self.log.info("开始执行Pytest测试...")

        # Pytest命令
        pytest_cmd = [
            "python", "-m", "pytest",
            self.suite_abs_path,
            f"--device_id={self.device_id}",
            f"--task_id={self.task_id}",
            f"--alluredir={self.allure_raw_dir}",
            "-v",
            "--tb=short",
            f"--timeout={GlobalConfig['test']['pytest_timeout']}"
        ]

        # 执行命令
        start_time = time.time()
        try:
            result = subprocess.run(
                pytest_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=GlobalConfig["test"]["pytest_timeout"] + 60
            )
            exec_duration = round(time.time() - start_time, 2)
            self.log.info(f"Pytest执行完成（耗时：{exec_duration}秒，返回码：{result.returncode}）")
        except subprocess.TimeoutExpired as e:
            exec_duration = round(time.time() - start_time, 2)
            self.log.error(f"Pytest执行超时（耗时：{exec_duration}秒，超过{GlobalConfig['test']['pytest_timeout']}秒）")
            raise

        # 保存执行日志
        with open(self.task_log_path, "w", encoding="utf-8") as f:
            log_content = [
                f"=== 任务{self.task_id} Pytest执行日志 ===",
                f"执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"执行耗时：{exec_duration}秒",
                f"执行命令：{' '.join(pytest_cmd)}",
                f"返回码：{result.returncode}",
                "\n=== 标准输出（stdout）===",
                result.stdout.strip() if result.stdout else "无输出",
                "\n=== 错误输出（stderr）===",
                result.stderr.strip() if result.stderr else "无错误输出"
            ]
            f.write("\n".join(log_content))

        # 校验Allure原始数据
        if not os.listdir(self.allure_raw_dir):
            self.log.warning("Allure原始报告目录为空，可能Pytest未生成测试结果")

        self.log.info(f"Pytest日志已保存：{self.task_log_path}（大小：{get_file_size(self.task_log_path):.2f}KB）")
        return result.returncode, result.stdout, result.stderr

    def _generate_allure_cmd(self) -> list:
        """构建Allure报告生成命令"""
        allure_cmd = [
            "allure", "generate",
            self.allure_raw_dir,
            "-o", self.allure_html_dir
        ]
        if self.allure_config["clean_before_generate"]:
            allure_cmd.append("--clean")
            self.log.debug("Allure生成命令包含--clean参数")
        if GlobalConfig.get("allure", {}).get("report_title"):
            report_title = GlobalConfig["allure"]["report_title"].replace("{{task_id}}", self.task_id)
            allure_cmd.extend(["--title", report_title])
            self.log.debug(f"Allure报告标题：{report_title}")
        return allure_cmd

    def _save_allure_log(self, cmd: list, stdout: str, stderr: str, duration: float) -> None:
        """保存Allure命令执行日志"""
        log_content = [
            f"=== 任务{self.task_id} Allure报告生成日志 ===",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"生成耗时：{duration}秒",
            f"执行命令：{' '.join(cmd)}",
            "\n=== 标准输出（stdout）===",
            stdout.strip() if stdout else "无输出",
            "\n=== 错误输出（stderr）===",
            stderr.strip() if stderr else "无错误输出"
        ]
        with open(self.allure_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_content))
        self.log.info(f"Allure生成日志已保存：{self.allure_log_path}")

    def _compress_html_report(self) -> Optional[str]:
        """压缩HTML报告"""
        if not self.allure_config["report_compress"]:
            self.log.debug("报告压缩功能已禁用")
            return None

        if not os.path.exists(self.allure_html_dir):
            self.log.warning("HTML报告目录不存在，跳过压缩")
            return None

        # 构建压缩包路径
        compress_name = f"allure_html_{self.task_id}.{self.allure_config['compress_format']}"
        compress_path = safe_join(self.task_report_dir, compress_name)

        try:
            start_time = time.time()
            shutil.make_archive(
                base_name=compress_path.replace(f".{self.allure_config['compress_format']}", ""),
                format=self.allure_config["compress_format"],
                root_dir=self.allure_html_dir
            )
            compress_duration = round(time.time() - start_time, 2)
            compress_size = get_file_size(compress_path)
            self.log.info(
                f"HTML报告压缩完成：{compress_path}（大小：{compress_size:.2f}MB，耗时：{compress_duration}秒）"
            )

            # 压缩后删除原始HTML目录（可选）
            if not self.allure_config["keep_raw_data"]:
                shutil.rmtree(self.allure_html_dir)
                self.log.debug(f"已删除原始HTML目录：{self.allure_html_dir}")

            return compress_path
        except Exception as e:
            self.log.error(f"HTML报告压缩失败：{str(e)[:300]}", exc_info=True)
            return None

    def _save_report_meta(self, report_info: Dict) -> None:
        """保存报告元数据"""
        meta_data = {
            "task_id": self.task_id,
            "device_id": self.device_id,
            "suite_path": self.suite_abs_path,
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "report_config": self.allure_config,
            "report_info": report_info,
            "file_stats": {
                "task_log_size_mb": round(get_file_size(self.task_log_path) / 1024, 4) if os.path.exists(self.task_log_path) else 0,
                "allure_log_size_mb": round(get_file_size(self.allure_log_path) / 1024, 4) if os.path.exists(self.allure_log_path) else 0,
                "raw_data_count": len(os.listdir(self.allure_raw_dir)) if os.path.exists(self.allure_raw_dir) else 0
            }
        }

        try:
            with open(self.report_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            self.log.info(f"报告元数据已保存：{self.report_meta_path}")
        except Exception as e:
            self.log.error(f"报告元数据保存失败：{str(e)}", exc_info=True)

    def generate_allure_report(self) -> Dict:
        """生成Allure HTML报告"""
        self.log.info("开始生成Allure HTML报告...")
        report_result = {
            "status": "failed",
            "index_path": None,
            "compress_path": None,
            "error_msg": None,
            "generate_duration": 0
        }

        # 构建Allure命令
        allure_cmd = self._generate_allure_cmd()
        self.log.debug(f"Allure生成命令：{' '.join(allure_cmd)}")

        # 校验Allure原始报告目录
        if not os.path.exists(self.allure_raw_dir):
            raise FileNotFoundError(f"Allure原始报告目录不存在：{self.allure_raw_dir}")
        if not os.access(self.allure_raw_dir, os.R_OK | os.W_OK):
            raise PermissionError(f"无权限读写Allure原始报告目录：{self.allure_raw_dir}")

        # 执行Allure命令
        start_time = time.time()
        try:
            result = subprocess.run(
                allure_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.allure_config["generate_timeout"],
                shell=True
            )
            report_result["generate_duration"] = round(time.time() - start_time, 2)

            # 保存Allure执行日志
            self._save_allure_log(
                cmd=allure_cmd,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=report_result["generate_duration"]
            )

            # 校验命令执行结果
            if result.returncode != 0:
                error_msg = f"Allure命令执行失败（返回码：{result.returncode}），错误详情：{result.stderr[:500]}"
                report_result["error_msg"] = error_msg
                raise RuntimeError(error_msg)

            # 校验报告入口文件
            index_html = safe_join(self.allure_html_dir, "index.html")
            if not os.path.exists(index_html):
                error_msg = f"报告入口文件不存在：{index_html}"
                report_result["error_msg"] = error_msg
                raise FileNotFoundError(error_msg)

            # 压缩HTML报告
            compress_path = self._compress_html_report()
            if compress_path:
                report_result["compress_path"] = compress_path

            # 更新报告结果状态
            report_result["status"] = "success"
            report_result["index_path"] = index_html
            report_size = get_file_size(self.allure_html_dir)
            self.log.info(
                f"Allure报告生成成功：{index_html}（目录大小：{report_size:.2f}MB，耗时：{report_result['generate_duration']}秒）"
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Allure报告生成超时（超过{self.allure_config['generate_timeout']}秒）"
            report_result["error_msg"] = error_msg
            self.log.error(error_msg)
        except Exception as e:
            error_msg = str(e)[:500]
            report_result["error_msg"] = error_msg
            self.log.error(f"Allure报告生成失败：{error_msg}", exc_info=True)
        finally:
            # 保存报告元数据
            self._save_report_meta(report_result)

        return report_result

    def execute(self) -> dict:
        """完整执行测试流程"""
        try:
            self.prepare()

            # 执行Pytest
            pytest_returncode, pytest_stdout, pytest_stderr = self.run_pytest()

            # 生成报告
            report_result = self.generate_allure_report()

            # 构建返回结果
            return {
                "status": "success" if (pytest_returncode == 0 and report_result["status"] == "success")
                          else "success_with_failure" if report_result["status"] == "success"
                          else "failed: report_generate_error",
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "report_path": self.allure_html_dir,
                "report_index_path": report_result["index_path"],
                "report_compress_path": report_result["compress_path"],
                "report_meta_path": self.report_meta_path,
                "log_path": self.task_log_path,
                "allure_log_path": self.allure_log_path,
                "pytest_returncode": pytest_returncode,
                "pytest_stdout": pytest_stdout,
                "pytest_stderr": pytest_stderr,
                "report_generate_duration": report_result["generate_duration"],
                "report_error_msg": report_result["error_msg"]
            }
        except subprocess.TimeoutExpired:
            error_msg = f"测试执行超时（超过{GlobalConfig['test']['pytest_timeout']}秒）"
            self.log.error(error_msg)
            return self._fail_result(error_msg)
        except Exception as e:
            error_msg = str(e)[:500]
            self.log.error(f"测试执行失败：{error_msg}", exc_info=True)
            return self._fail_result(error_msg)

    def _fail_result(self, error_msg: str) -> dict:
        """生成失败结果字典"""
        log_files = {
            "task_log_path": self.task_log_path if os.path.exists(self.task_log_path) else None,
            "allure_log_path": self.allure_log_path if os.path.exists(self.allure_log_path) else None,
            "report_meta_path": self.report_meta_path if os.path.exists(self.report_meta_path) else None
        }

        return {
            "status": f"failed: {error_msg}",
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_msg": error_msg,** log_files,
            "report_path": self.allure_html_dir if os.path.exists(self.allure_html_dir) else None,
            "pytest_returncode": -1,
            "report_generate_duration": 0
        }