# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
import traceback
import uuid
import time
import shutil
import json
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
from threading import Thread
from core.test_executor import TestExecutor
from core.device_manager import DeviceManager
from util.log_util import TempLog
from util.path_util import safe_join, ensure_dir_exists, get_report_root

test_bp = Blueprint("test", __name__)
test_tasks = {}  # 全局任务状态缓存（task_id: 任务信息）
log = TempLog()


# ------------------- 工具函数 -------------------
def get_task_id() -> str:
    """生成唯一任务ID（毫秒级时间戳+4位随机字符串）"""
    time_part = datetime.now().strftime("%Y%m%d%H%M%S%f")[:13]
    random_part = str(uuid.uuid4()).replace("-", "")[:4]
    return f"{time_part}_{random_part}"


def get_test_suites() -> list[dict]:
    """获取测试用例列表（从配置的TEST_SUITE_DIR读取）"""
    try:
        test_suite_dir = current_app.config["TEST_SUITE_DIR"]
        log.info(f"开始获取测试用例，目录：{test_suite_dir}")

        # 确保用例目录存在
        if not os.path.exists(test_suite_dir):
            os.makedirs(test_suite_dir, exist_ok=True)
            log.warning(f"用例目录不存在，已自动创建：{test_suite_dir}")

        suites = []
        # 遍历目录，筛选.py文件（排除conftest.py）
        for root, _, files in os.walk(test_suite_dir):
            for name in files:
                if name.endswith(".py") and name != "conftest.py":
                    abs_path = safe_join(root, name)  # 安全路径拼接
                    rel_path = os.path.relpath(abs_path, test_suite_dir)
                    suites.append({
                        "id": len(suites),
                        "name": name,
                        "abs_path": abs_path,
                        "rel_path": rel_path
                    })

        log.info(f"获取用例完成，共{len(suites)}个可用用例")
        return suites
    except Exception as e:
        error_msg = f"获取用例列表失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return []


def run_task_background(task_id: str, device_id: str, suite_abs_path: str) -> None:
    """后台执行测试任务（独立线程）"""
    # 更新任务状态为"running"
    test_tasks[task_id]["status"] = "running"
    test_tasks[task_id]["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # 1. 获取设备实例（确保初始化成功）
        DeviceManager.get_uiautomator_instance(device_id, task_id)

        # 2. 执行测试
        executor = TestExecutor(task_id, device_id, suite_abs_path)
        task_result = executor.execute()

        # 3. 更新任务结果
        test_tasks[task_id].update(task_result)
    finally:
        # 4. 释放设备实例（无论成功失败）
        DeviceManager.release_device(device_id)


def monitor_exec_set_report(main_task_id: str, device_id: str, sub_task_ids: list[str]) -> None:
    """
    监控执行集内所有子任务，全部结束后汇总Allure原始数据并生成一份执行集报告。
    报告目录：与单任务一致，位于 report_root/<main_task_id>/allure_html
    """
    try:
        log.info(f"执行集主任务{main_task_id}开始监控子任务：{sub_task_ids}")

        # 等待所有子任务结束（pending/running -> 结束状态）
        while True:
            all_done = True
            for sid in sub_task_ids:
                task = test_tasks.get(sid)
                if not task or task.get("status") in ("pending", "running"):
                    all_done = False
                    break
            if all_done:
                break
            time.sleep(2)

        # 若没有任何子任务，直接标记失败
        if not sub_task_ids:
            log.warning(f"执行集主任务{main_task_id}无子任务，无法生成报告")
            main_task = test_tasks.get(main_task_id, {})
            main_task.update(
                {
                    "status": "failed",
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "report_error_msg": "执行集无子任务，未生成报告",
                }
            )
            test_tasks[main_task_id] = main_task
            return

        first_sub_task = test_tasks.get(sub_task_ids[0])
        if not first_sub_task or "suite_info" not in first_sub_task:
            log.error(f"执行集主任务{main_task_id}无法获取首个子任务信息，跳过报告生成")
            return

        first_suite = first_sub_task["suite_info"]
        executor = TestExecutor(main_task_id, device_id, first_suite["abs_path"])

        # 准备主任务的报告目录结构（不执行pytest，只做报告）
        ensure_dir_exists(executor.task_report_dir)
        ensure_dir_exists(executor.allure_raw_dir)
        ensure_dir_exists(executor.allure_html_dir)

        # 汇总所有子任务的Allure原始数据
        merged_count = 0
        for sid in sub_task_ids:
            sub_raw_dir = safe_join(executor.report_root, sid, "allure_raw")
            if not os.path.exists(sub_raw_dir):
                log.warning(f"子任务{sub_task_ids}的Allure原始目录不存在：{sub_raw_dir}")
                continue
            for name in os.listdir(sub_raw_dir):
                src = safe_join(sub_raw_dir, name)
                if not os.path.isfile(src):
                    continue
                dst_name = f"{sid}_{name}"
                dst = safe_join(executor.allure_raw_dir, dst_name)
                shutil.copy2(src, dst)
                merged_count += 1

        if merged_count == 0:
            log.warning(f"执行集主任务{main_task_id}未汇总到任何Allure原始数据，跳过报告生成")
            main_task = test_tasks.get(main_task_id, {})
            main_task.update(
                {
                    "status": "failed",
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "report_error_msg": "未找到子任务Allure原始数据，未生成报告",
                }
            )
            test_tasks[main_task_id] = main_task
            return

        log.info(
            f"执行集主任务{main_task_id}开始生成汇总报告，合并原始事件文件数：{merged_count}"
        )
        report_result = executor.generate_allure_report()

        # 汇总整体状态：只要有子任务失败，则标记为failed，否则success
        any_failed = any(
            "failed" in (test_tasks.get(sid, {}).get("status") or "")
            for sid in sub_task_ids
        )
        overall_status = (
            "success" if (report_result["status"] == "success" and not any_failed) else "failed"
        )

        main_task = test_tasks.get(main_task_id, {})
        main_task.update(
            {
                "status": overall_status,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "report_path": executor.allure_html_dir,
                "report_index_path": report_result.get("index_path"),
                "report_meta_path": executor.report_meta_path,
                "report_generate_duration": report_result.get("generate_duration", 0),
                "report_error_msg": report_result.get("error_msg"),
            }
        )
        test_tasks[main_task_id] = main_task

        log.info(
            f"执行集主任务{main_task_id}汇总报告生成完成，状态：{overall_status}，入口：{report_result.get('index_path')}"
        )
    except Exception as e:
        log.error(f"执行集主任务{main_task_id}生成汇总报告失败：{str(e)}", exc_info=True)
        main_task = test_tasks.get(main_task_id, {})
        main_task.update(
            {
                "status": "failed",
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "report_error_msg": f"执行集报告生成异常：{str(e)}",
            }
        )
        test_tasks[main_task_id] = main_task


# ------------------- 接口定义 -------------------
@test_bp.get("/suites")
def get_test_suite_list():
    """获取测试用例列表接口"""
    try:
        log.info("收到测试用例列表查询请求")
        suites = get_test_suites()
        return jsonify({
            "code": 200,
            "msg": f"获取用例成功（共{len(suites)}个）",
            "data": suites
        })
    except Exception as e:
        error_msg = f"获取用例列表失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": []
        })


@test_bp.post("/start")
def start_test():
    """启动测试任务接口"""
    try:
        # 1. 解析请求参数
        req_data = request.get_json() or {}
        device_id = req_data.get("device_id")
        suite_id = req_data.get("suite_id")

        # 2. 参数校验
        if not device_id:
            return jsonify({"code": 400, "msg": "请指定设备ID", "data": None})
        if suite_id is None:
            return jsonify({"code": 400, "msg": "请指定用例ID", "data": None})

        # 3. 获取用例路径
        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例ID{suite_id}不存在", "data": None})
        suite_info = suites[suite_id]

        # 4. 创建任务
        task_id = get_task_id()
        test_tasks[task_id] = {
            "task_id": task_id,
            "device_id": device_id,
            "suite_info": suite_info,
            "status": "pending",  # pending/running/success/failed
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 5. 后台启动任务（避免阻塞Web请求）
        Thread(
            target=run_task_background,
            args=(task_id, device_id, suite_info["abs_path"]),
            daemon=True  # 守护线程，Web服务退出时自动结束
        ).start()

        log.info(f"任务{task_id}创建成功（设备：{device_id}，用例：{suite_info['name']}）")
        return jsonify({
            "code": 200,
            "msg": "测试任务已启动",
            "data": {"task_id": task_id}
        })
    except Exception as e:
        error_msg = f"启动测试任务失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })


@test_bp.get("/status/<task_id>")
def get_task_status(task_id: str):
    """查询测试任务状态接口"""
    try:
        task = test_tasks.get(task_id)
        if not task:
            # 兼容：服务重启/内存丢失时，从 report_meta.json 恢复已完成任务状态
            try:
                report_root = get_report_root()
                report_meta_path = safe_join(report_root, task_id, "report_meta.json")
                if os.path.exists(report_meta_path):
                    with open(report_meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)

                    report_info = meta.get("report_info") or {}
                    index_path = report_info.get("index_path")
                    report_dir = os.path.dirname(index_path) if index_path else None

                    status = "success" if report_info.get("status") == "success" else "failed"

                    restored_task = {
                        "task_id": meta.get("task_id", task_id),
                        "device_id": meta.get("device_id"),
                        "status": status,
                        "end_time": meta.get("generate_time"),
                        "report_path": report_dir,
                        "report_index_path": index_path,
                        "report_meta_path": report_meta_path,
                    }
                    if restored_task.get("report_path"):
                        restored_task["report_url"] = f"/api/report/files/{task_id}/index.html"

                    return jsonify(
                        {
                            "code": 200,
                            "msg": "查询任务状态成功（已从报告元数据恢复）",
                            "data": restored_task,
                        }
                    )
            except Exception as e:
                log.error(f"从报告元数据恢复任务{task_id}失败：{str(e)}", exc_info=True)

            return jsonify(
                {
                    "code": 404,
                    "msg": f"任务{task_id}不存在",
                    "data": None,
                }
            )

        # 补充报告访问URL（若任务成功）
        if "report_path" in task and task["report_path"]:
            task["report_url"] = f"/api/report/files/{task_id}/index.html"

        return jsonify({
            "code": 200,
            "msg": "查询任务状态成功",
            "data": task
        })
    except Exception as e:
        error_msg = f"查询任务{task_id}状态失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })


@test_bp.get("/running")
def get_running_tasks():
    """获取所有运行中任务"""
    try:
        running_tasks = [
            task for task in test_tasks.values()
            if task["status"] == "running"
        ]
        return jsonify({
            "code": 200,
            "msg": f"获取运行中任务成功（共{len(running_tasks)}个）",
            "data": running_tasks
        })
    except Exception as e:
        error_msg = f"获取运行中任务失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": []
        })


@test_bp.post("/stop/<task_id>")
def stop_test_task(task_id: str):
    """停止指定测试任务"""
    try:
        task = test_tasks.get(task_id)
        if not task:
            return jsonify({
                "code": 404,
                "msg": f"任务{task_id}不存在",
                "data": None
            })

        if task["status"] != "running":
            return jsonify({
                "code": 400,
                "msg": f"任务{task_id}不在运行中，状态：{task['status']}",
                "data": None
            })

        # 实际项目中需要实现真正的任务停止逻辑
        # 这里只是模拟停止操作
        task["status"] = "stopped"
        task["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task["stop_reason"] = "用户手动停止"

        log.info(f"任务{task_id}已被手动停止")
        return jsonify({
            "code": 200,
            "msg": f"任务{task_id}已停止",
            "data": {"task_id": task_id}
        })
    except Exception as e:
        error_msg = f"停止任务{task_id}失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })


@test_bp.get("/suite/<int:suite_id>")
def get_test_suite(suite_id):
    """获取单个测试用例内容"""
    try:
        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例不存在", "data": None})

        suite_info = suites[suite_id]
        with open(suite_info["abs_path"], "r", encoding="utf-8") as f:
            content = f.read()

        return jsonify({
            "code": 200,
            "msg": "获取用例内容成功",
            "data": {
                "id": suite_id,
                "name": suite_info["name"],
                "content": content,
                "abs_path": suite_info["abs_path"],
                "rel_path": suite_info["rel_path"]
            }
        })
    except Exception as e:
        error_msg = f"获取用例内容失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/suite")
def create_test_suite():
    """创建新测试用例"""
    try:
        req_data = request.get_json() or {}
        name = req_data.get("name")
        content = req_data.get("content", "")

        if not name or not name.endswith(".py"):
            return jsonify({"code": 400, "msg": "用例名称必须以.py结尾", "data": None})

        test_suite_dir = current_app.config["TEST_SUITE_DIR"]
        file_path = safe_join(test_suite_dir, name)

        if os.path.exists(file_path):
            return jsonify({"code": 400, "msg": "用例已存在", "data": None})

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return jsonify({
            "code": 200,
            "msg": "用例创建成功",
            "data": {"name": name}
        })
    except Exception as e:
        error_msg = f"创建用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.put("/suite/<int:suite_id>")
def update_test_suite(suite_id):
    """更新测试用例内容"""
    try:
        req_data = request.get_json() or {}
        content = req_data.get("content")

        if content is None:
            return jsonify({"code": 400, "msg": "请提供用例内容", "data": None})

        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例不存在", "data": None})

        suite_info = suites[suite_id]
        with open(suite_info["abs_path"], "w", encoding="utf-8") as f:
            f.write(content)

        return jsonify({
            "code": 200,
            "msg": "用例更新成功",
            "data": None
        })
    except Exception as e:
        error_msg = f"更新用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.delete("/suite/<int:suite_id>")
def delete_test_suite(suite_id):
    """删除测试用例"""
    try:
        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例不存在", "data": None})

        suite_info = suites[suite_id]
        os.remove(suite_info["abs_path"])

        return jsonify({
            "code": 200,
            "msg": "用例删除成功",
            "data": None
        })
    except Exception as e:
        error_msg = f"删除用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.get("/suites/<int:suite_id>/content")
def get_suite_content(suite_id):
    """获取测试用例内容"""
    try:
        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例ID{suite_id}不存在", "data": None})

        suite_info = suites[suite_id]
        with open(suite_info["abs_path"], "r", encoding="utf-8") as f:
            content = f.read()

        return jsonify({
            "code": 200,
            "msg": "获取用例内容成功",
            "data": {
                "content": content,
                "path": suite_info["rel_path"]
            }
        })
    except Exception as e:
        error_msg = f"获取用例内容失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })


@test_bp.put("/suites/<int:suite_id>")
def update_suite(suite_id):
    """更新测试用例"""
    try:
        req_data = request.get_json() or {}
        new_name = req_data.get("name")
        new_content = req_data.get("content")

        if not new_name or new_content is None:
            return jsonify({"code": 400, "msg": "名称和内容不能为空", "data": None})

        suites = get_test_suites()
        if suite_id < 0 or suite_id >= len(suites):
            return jsonify({"code": 404, "msg": f"用例ID{suite_id}不存在", "data": None})

        suite_info = suites[suite_id]
        file_path = suite_info["abs_path"]

        # 确保文件名有效
        new_file_name = f"{new_name.replace(' ', '_')}.py"
        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)

        # 保存文件内容
        with open(new_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 如果文件名改变，删除旧文件
        if new_file_path != file_path:
            os.remove(file_path)

        log.info(f"用例{suite_id}更新成功，路径：{new_file_path}")
        return jsonify({
            "code": 200,
            "msg": "用例更新成功",
            "data": None
        })
    except Exception as e:
        error_msg = f"更新用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })


@test_bp.post("/format-code")
def format_code():
    """代码格式化接口"""
    try:
        req_data = request.get_json() or {}
        code = req_data.get("code", "")

        # 使用black进行代码格式化
        import black
        from black import Mode

        formatted_code = black.format_str(code, mode=Mode())

        return jsonify({
            "code": 200,
            "msg": "代码格式化成功",
            "data": {"formatted_code": formatted_code}
        })
    except Exception as e:
        error_msg = f"代码格式化失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": None
        })

# 新增导入
from core.exec_set_manager import ExecSetManager

# ------------------- 执行集接口 -------------------
@test_bp.get("/exec-sets")
def get_exec_sets():
    """获取所有执行集"""
    try:
        exec_sets = ExecSetManager.get_all_exec_sets()
        return jsonify({
            "code": 200,
            "msg": f"获取执行集成功（共{len(exec_sets)}个）",
            "data": exec_sets
        })
    except Exception as e:
        error_msg = f"获取执行集失败：{str(e)}"
        log.error(error_msg)
        return jsonify({
            "code": 400,
            "msg": error_msg,
            "data": []
        })


@test_bp.get("/exec-set/<exec_set_id>")
def get_exec_set_detail(exec_set_id):
    """获取执行集详情（含用例列表）"""
    try:
        exec_set = ExecSetManager.get_exec_set_by_id(exec_set_id)
        if not exec_set:
            return jsonify({"code": 404, "msg": "执行集不存在", "data": None})
        return jsonify({
            "code": 200,
            "msg": "获取执行集详情成功",
            "data": exec_set
        })
    except Exception as e:
        error_msg = f"获取执行集详情失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/exec-set")
def create_exec_set():
    """创建执行集"""
    try:
        req_data = request.get_json() or {}
        name = req_data.get("name")
        desc = req_data.get("description", "")

        if not name:
            return jsonify({"code": 400, "msg": "执行集名称不能为空", "data": None})

        exec_set = ExecSetManager.create_exec_set(name, desc)
        if not exec_set:
            return jsonify({"code": 400, "msg": "执行集名称已存在", "data": None})

        return jsonify({
            "code": 200,
            "msg": "创建执行集成功",
            "data": exec_set
        })
    except Exception as e:
        error_msg = f"创建执行集失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.put("/exec-set/<exec_set_id>")
def update_exec_set(exec_set_id):
    """更新执行集基本信息"""
    try:
        req_data = request.get_json() or {}
        name = req_data.get("name")
        desc = req_data.get("description")

        success = ExecSetManager.update_exec_set(exec_set_id, name, desc)
        if success:
            return jsonify({"code": 200, "msg": "更新执行集成功", "data": None})
        return jsonify({"code": 400, "msg": "更新失败（名称重复或执行集不存在）", "data": None})
    except Exception as e:
        error_msg = f"更新执行集失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/exec-set/<exec_set_id>/cases")
def add_cases_to_exec_set(exec_set_id):
    """
    覆盖设置指定执行集中的用例列表（按测试用例文件维度）

    请求体格式示例：
    {
        "suite_ids": [0, 1, 2]  # 必填：测试用例ID列表（对应 /api/test/suites 返回的 id）
    }
    """
    try:
        req_data = request.get_json() or {}
        suite_ids = req_data.get("suite_ids")

        if not isinstance(suite_ids, list) or not suite_ids:
            return jsonify(
                {
                    "code": 400,
                    "msg": "suite_ids 必须为非空列表（元素为用例ID，整数）",
                    "data": None,
                }
            )

        # 将所有ID转为整数，避免类型问题
        try:
            suite_ids_int = {int(sid) for sid in suite_ids}
        except (TypeError, ValueError):
            return jsonify(
                {
                    "code": 400,
                    "msg": "suite_ids 中包含非法ID（必须为整数）",
                    "data": None,
                }
            )

        # 基于当前用例列表构建要写入执行集的用例信息
        all_suites = get_test_suites()
        suite_map = {s["id"]: s for s in all_suites}

        missing_ids = [sid for sid in suite_ids_int if sid not in suite_map]
        if missing_ids:
            return jsonify(
                {
                    "code": 404,
                    "msg": f"以下用例ID不存在：{missing_ids}",
                    "data": None,
                }
            )

        cases = []
        for sid in suite_ids_int:
            s = suite_map[sid]
            cases.append(
                {
                    "suite_id": s["id"],
                    "abs_path": s["abs_path"],
                    "name": s.get("name"),
                    "rel_path": s.get("rel_path"),
                }
            )

        success = ExecSetManager.set_cases_for_exec_set(exec_set_id, cases)
        if not success:
            return jsonify(
                {
                    "code": 404,
                    "msg": "执行集不存在，或更新失败",
                    "data": None,
                }
            )

        log.info(
            f"执行集[{exec_set_id}]用例列表已更新：suite_ids={sorted(list(suite_ids_int))}"
        )

        return jsonify(
            {
                "code": 200,
                "msg": "执行集用例列表更新成功",
                "data": {
                    "exec_set_id": exec_set_id,
                    "case_count": len(cases),
                },
            }
        )
    except Exception as e:
        log.error(f"设置执行集用例失败：{str(e)}", exc_info=True)
        return jsonify(
            {
                "code": 500,
                "msg": f"设置执行集用例失败：{str(e)}",
                "data": None,
            }
        )


@test_bp.delete("/exec-set/<exec_set_id>/case/<int:suite_id>")
def remove_case_from_exec_set(exec_set_id, suite_id):
    """从执行集中移除用例"""
    try:
        success = ExecSetManager.remove_case_from_exec_set(exec_set_id, suite_id)
        if success:
            return jsonify({"code": 200, "msg": "移除用例成功", "data": None})
        return jsonify({"code": 404, "msg": "执行集或用例不存在", "data": None})
    except Exception as e:
        error_msg = f"移除执行集用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.delete("/exec-set/<exec_set_id>")
def delete_exec_set(exec_set_id):
    """删除执行集"""
    try:
        success = ExecSetManager.delete_exec_set(exec_set_id)
        if success:
            return jsonify({"code": 200, "msg": "删除执行集成功", "data": None})
        return jsonify({"code": 404, "msg": "执行集不存在", "data": None})
    except Exception as e:
        error_msg = f"删除执行集失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/start-exec-set")
def start_exec_set_test():
    """通过执行集启动测试（批量执行用例）"""
    try:
        # 1. 解析参数
        req_data = request.get_json() or {}
        device_id = req_data.get("device_id")
        exec_set_id = req_data.get("exec_set_id")

        if not device_id or not exec_set_id:
            return jsonify({"code": 400, "msg": "请指定设备ID和执行集ID", "data": None})

        # 2. 获取执行集详情
        exec_set = ExecSetManager.get_exec_set_by_id(exec_set_id)
        if not exec_set or len(exec_set["cases"]) == 0:
            return jsonify({"code": 400, "msg": "执行集不存在或无可用用例", "data": None})

        # 3. 生成批量任务ID（主任务ID + 子任务ID）
        main_task_id = get_task_id()
        sub_tasks = []

        # 4. 批量创建子任务（每个用例一个子任务）
        for case in exec_set["cases"]:
            sub_task_id = get_task_id()
            test_tasks[sub_task_id] = {
                "task_id": sub_task_id,
                "main_task_id": main_task_id,
                "device_id": device_id,
                "suite_info": case,
                "status": "pending",
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            # 后台启动子任务
            Thread(
                target=run_task_background,
                args=(sub_task_id, device_id, case["abs_path"]),
                daemon=True
            ).start()
            sub_tasks.append(sub_task_id)

        # 5. 记录主任务
        test_tasks[main_task_id] = {
            "task_id": main_task_id,
            "type": "exec_set",
            "exec_set_id": exec_set_id,
            "exec_set_name": exec_set["name"],
            "device_id": device_id,
            "sub_tasks": sub_tasks,
            "status": "running",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "case_count": len(sub_tasks)
        }

        # 6. 后台启动执行集报告汇总线程
        Thread(
            target=monitor_exec_set_report,
            args=(main_task_id, device_id, sub_tasks),
            daemon=True,
        ).start()

        log.info(f"执行集任务{main_task_id}启动成功（设备：{device_id}，执行集：{exec_set['name']}，用例数：{len(sub_tasks)}）")
        return jsonify({
            "code": 200,
            "msg": "执行集测试任务已启动",
            "data": {
                "main_task_id": main_task_id,
                "sub_task_count": len(sub_tasks),
                "exec_set_name": exec_set["name"]
            }
        })
    except Exception as e:
        error_msg = f"启动执行集测试失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})