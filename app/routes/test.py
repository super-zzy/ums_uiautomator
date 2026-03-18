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
from core import db

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
    """获取测试用例列表（仅从SQLite读取）"""
    try:
        # 仅从SQLite读取已有用例
        suites = db.list_cases()

        # 统一返回前端需要的结构（补充创建/更新时间，便于前端展示）
        # 不再依赖持久化的文件路径信息，按用例名称展示
        log.info(f"获取用例完成（仅SQLite），共{suites and len(suites) or 0}个可用用例")
        return [
            {
                "id": s["id"],
                "name": s["name"],
                "abs_path": "",
                "rel_path": s.get("name") or "",
                # 旧数据可能缺少 updated_at，这里做一个兜底：若为空则回退到 created_at
                "created_at": s.get("created_at") or "",
                "updated_at": s.get("updated_at") or s.get("created_at") or "",
            }
            for s in suites
        ]
    except Exception as e:
        error_msg = f"获取用例列表失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return []


def run_task_background(task_id: str, device_id: str, suite_abs_path: str) -> None:
    """后台执行测试任务（独立线程）"""
    # 更新任务状态为"running"
    test_tasks[task_id]["status"] = "running"
    test_tasks[task_id]["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 同步到执行历史与运行时任务表
    try:
        db.upsert_history(
            task_id=task_id,
            status="running",
            start_time=test_tasks[task_id]["start_time"],
        )
        db.upsert_task_runtime(
            task_id=task_id,
            status="running",
            start_time=test_tasks[task_id]["start_time"],
        )
    except Exception as e:
        log.error(f"更新任务{task_id}历史状态为running失败：{str(e)}", exc_info=True)

    try:
        # 1. 获取设备实例（确保初始化成功）
        DeviceManager.get_uiautomator_instance(device_id, task_id)

        # 2. 执行测试
        executor = TestExecutor(task_id, device_id, suite_abs_path)
        task_result = executor.execute()

        # 3. 更新任务结果
        test_tasks[task_id].update(task_result)
        # 计算本次执行耗时（秒）
        exec_duration = None
        try:
            start_str = test_tasks[task_id].get("start_time")
            end_str = task_result.get("end_time")
            if start_str and end_str:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                exec_duration = max((end_dt - start_dt).total_seconds(), 0.0)
        except Exception:
            exec_duration = None
        # 写入/更新执行历史与运行时任务
        try:
            db.upsert_history(
                task_id=task_id,
                status=task_result.get("status"),
                end_time=task_result.get("end_time"),
                exec_duration=exec_duration,
                report_index_path=task_result.get("report_index_path"),
                report_meta_path=task_result.get("report_meta_path"),
                pytest_returncode=task_result.get("pytest_returncode"),
                report_generate_duration=task_result.get("report_generate_duration"),
                error_msg=task_result.get("error_msg"),
            )
            db.upsert_task_runtime(
                task_id=task_id,
                status=task_result.get("status"),
                end_time=task_result.get("end_time"),
            )
        except Exception as e:
            log.error(f"写入任务{task_id}执行历史失败：{str(e)}", exc_info=True)
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
                    "status": "failure",
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "report_error_msg": "执行集无子任务，未生成报告",
                }
            )
            test_tasks[main_task_id] = main_task
            try:
                db.upsert_history(
                    task_id=main_task_id,
                    status="failure",
                    end_time=main_task["end_time"],
                    error_msg=main_task["report_error_msg"],
                )
            except Exception as e:
                log.error(f"写入执行集主任务{main_task_id}历史失败：{str(e)}", exc_info=True)
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
                    "status": "failure",
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "report_error_msg": "未找到子任务Allure原始数据，未生成报告",
                }
            )
            test_tasks[main_task_id] = main_task
            try:
                db.upsert_history(
                    task_id=main_task_id,
                    status="failure",
                    end_time=main_task["end_time"],
                    error_msg=main_task["report_error_msg"],
                )
            except Exception as e:
                log.error(f"写入执行集主任务{main_task_id}历史失败：{str(e)}", exc_info=True)
            return

        log.info(
            f"执行集主任务{main_task_id}开始生成汇总报告，合并原始事件文件数：{merged_count}"
        )
        report_result = executor.generate_allure_report()

        # 汇总整体状态：只要有子任务失败，则标记为failed，否则success
        any_failed = any(
            "failure" in (test_tasks.get(sid, {}).get("status") or "")
            or "failed" in (test_tasks.get(sid, {}).get("status") or "")
            for sid in sub_task_ids
        )
        overall_status = (
            "success"
            if (report_result["status"] == "success" and not any_failed)
            else "failure"
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
        # 计算主任务执行耗时（秒）
        exec_duration = None
        try:
            start_str = main_task.get("start_time")
            end_str = main_task.get("end_time")
            if start_str and end_str:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                exec_duration = max((end_dt - start_dt).total_seconds(), 0.0)
        except Exception:
            exec_duration = None
        try:
            db.upsert_history(
                task_id=main_task_id,
                status=overall_status,
                end_time=main_task["end_time"],
                exec_duration=exec_duration,
                report_index_path=main_task.get("report_index_path"),
                report_meta_path=main_task.get("report_meta_path"),
                report_generate_duration=main_task.get("report_generate_duration"),
                error_msg=main_task.get("report_error_msg"),
            )
            # 同步更新运行时任务表中的主任务状态，避免任务管理中残留“运行中”记录
            db.upsert_task_runtime(
                task_id=main_task_id,
                status=overall_status,
                end_time=main_task["end_time"],
            )
        except Exception as e:
            log.error(f"写入执行集主任务{main_task_id}历史失败：{str(e)}", exc_info=True)

        log.info(
            f"执行集主任务{main_task_id}汇总报告生成完成，状态：{overall_status}，入口：{report_result.get('index_path')}"
        )
    except Exception as e:
        log.error(f"执行集主任务{main_task_id}生成汇总报告失败：{str(e)}", exc_info=True)
        main_task = test_tasks.get(main_task_id, {})
        main_task.update(
            {
                "status": "failure",
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "report_error_msg": f"执行集报告生成异常：{str(e)}",
            }
        )
        test_tasks[main_task_id] = main_task
        # 计算执行耗时（若有开始时间）
        exec_duration = None
        try:
            start_str = main_task.get("start_time")
            end_str = main_task.get("end_time")
            if start_str and end_str:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                exec_duration = max((end_dt - start_dt).total_seconds(), 0.0)
        except Exception:
            exec_duration = None
        try:
            db.upsert_history(
                task_id=main_task_id,
                status="failure",
                end_time=main_task["end_time"],
                exec_duration=exec_duration,
                error_msg=main_task["report_error_msg"],
            )
            # 同步更新运行时任务表中的主任务状态，避免任务管理中残留“运行中”记录
            db.upsert_task_runtime(
                task_id=main_task_id,
                status="failed",
                end_time=main_task["end_time"],
            )
        except Exception as e2:
            log.error(f"写入执行集主任务{main_task_id}历史失败：{str(e2)}", exc_info=True)


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
        # 兼容两种传参方式：
        # - 旧版：suite_id 为前端列表下标（0,1,2,...）
        # - 新版：suite_id 直接为 SQLite 中的用例主键 ID
        case = None
        suite_info = None

        # 3.1 优先按“用例主键ID”方式解析
        try:
            case = db.get_case(int(suite_id))
        except Exception:
            case = None

        if case:
            suite_info = {
                "id": case["id"],
                "name": case["name"],
                "file_name": case.get("file_name"),
                "rel_path": case.get("rel_path"),
            }
        else:
            # 3.2 回退到“列表下标”模式，兼容老前端
            suites = get_test_suites()
            if not isinstance(suite_id, int):
                try:
                    suite_id = int(suite_id)
                except Exception:
                    return jsonify(
                        {"code": 400, "msg": "用例ID格式不正确", "data": None}
                    )

            if suite_id < 0 or suite_id >= len(suites):
                return jsonify(
                    {"code": 404, "msg": f"用例ID{suite_id}不存在", "data": None}
                )
            suite_info = suites[suite_id]

            case = db.get_case(suite_info["id"])
            if not case:
                return jsonify({"code": 404, "msg": "用例不存在", "data": None})

        test_suite_dir = current_app.config["TEST_SUITE_DIR"]
        ensure_dir_exists(test_suite_dir)
        # 使用数据库中的file_name生成文件
        file_name = case.get("file_name") or f"case_{case['id']}.py"
        suite_abs_path = safe_join(test_suite_dir, file_name)
        with open(suite_abs_path, "w", encoding="utf-8") as f:
            f.write(case["content"])

        # 4. 创建任务
        task_id = get_task_id()
        test_tasks[task_id] = {
            "task_id": task_id,
            "device_id": device_id,
            "suite_info": suite_info,
            "status": "pending",  # pending/running/success/failed
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 写入执行历史与运行时任务（初始记录）
        try:
            db.upsert_history(
                task_id=task_id,
                device_id=device_id,
                case_id=case["id"],
                type_="single",
                status="pending",
                create_time=test_tasks[task_id]["create_time"],
            )
            db.upsert_task_runtime(
                task_id=task_id,
                main_task_id=None,
                type_="single",
                device_id=device_id,
                status="pending",
                create_time=test_tasks[task_id]["create_time"],
            )
        except Exception as e:
            log.error(f"写入任务{task_id}初始历史失败：{str(e)}", exc_info=True)

        # 5. 后台启动任务（避免阻塞Web请求）
        Thread(
            target=run_task_background,
            args=(task_id, device_id, suite_abs_path),
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

                    status = (
                        "success"
                        if report_info.get("status") == "success"
                        else "failure"
                    )

                    # 尝试从执行历史中补充用例名称，避免前端显示“未知用例”
                    case_name = None
                    try:
                        history = db.get_history_by_task_id(task_id)
                        if history and history.get("case_id"):
                            case = db.get_case(history["case_id"])
                            if case:
                                case_name = case.get("name")
                    except Exception as e:
                        log.warning(
                            f"根据历史记录补充任务{task_id}用例名称失败：{e}"
                        )

                    restored_task = {
                        "task_id": meta.get("task_id", task_id),
                        "device_id": meta.get("device_id"),
                        "status": status,
                        "end_time": meta.get("generate_time"),
                        "report_path": report_dir,
                        "report_index_path": index_path,
                        "report_meta_path": report_meta_path,
                        "suite_info": {
                            "name": case_name,
                        }
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


@test_bp.get("/history")
def get_history_list():
    """获取任务执行历史列表（支持分页）"""
    # 兼容：若传 limit 则走旧逻辑（返回 list）
    if request.args.get("limit") is not None and request.args.get("page") is None:
        try:
            limit = int(request.args.get("limit", 100))
            if limit <= 0:
                limit = 100
        except Exception:
            limit = 100
        try:
            histories = db.list_histories(limit=limit)
            return jsonify(
                {
                    "code": 200,
                    "msg": f"获取执行历史成功（最近{len(histories)}条）",
                    "data": histories,
                }
            )
        except Exception as e:
            error_msg = f"获取执行历史失败：{str(e)}"
            log.error(error_msg, exc_info=True)
            return jsonify({"code": 400, "msg": error_msg, "data": []})

    # 新逻辑：分页（仅单用例/子任务）
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))
    except Exception:
        page = 1
        page_size = 10
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    try:
        total = db.count_single_histories()
        items = db.list_single_histories_paginated(offset=offset, limit=page_size)
        total_pages = max((total + page_size - 1) // page_size, 1)
        return jsonify(
            {
                "code": 200,
                "msg": "获取执行历史成功",
                "data": {
                    "items": items,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                },
            }
        )
    except Exception as e:
        error_msg = f"获取执行历史失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify(
            {"code": 400, "msg": error_msg, "data": {"items": [], "total": 0}}
        )


@test_bp.get("/history/<task_id>")
def get_history_detail(task_id: str):
    """根据task_id获取单条执行历史"""
    try:
        history = db.get_history_by_task_id(task_id)
        if not history:
            return jsonify(
                {"code": 404, "msg": f"任务{task_id}无历史记录", "data": None}
            )
        return jsonify({"code": 200, "msg": "获取执行历史成功", "data": history})
    except Exception as e:
        error_msg = f"获取任务{task_id}执行历史失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/history/migrate-from-result")
def migrate_history_from_result():
    """
    将现有result目录下的历史report_meta.json导入SQLite的exec_history表。
    只依赖report_meta.json，不会修改原有报告结构。
    """
    try:
        report_root = get_report_root()
        imported = 0
        skipped = 0

        for entry in os.listdir(report_root):
            task_dir = os.path.join(report_root, entry)
            if not os.path.isdir(task_dir):
                continue
            meta_path = os.path.join(task_dir, "report_meta.json")
            if not os.path.exists(meta_path):
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e:
                log.warning(f"读取报告元数据失败，跳过：{meta_path}，错误：{e}")
                skipped += 1
                continue

            task_id = meta.get("task_id") or entry
            device_id = meta.get("device_id")
            generate_time = meta.get("generate_time")
            report_info = meta.get("report_info") or {}

            status = report_info.get("status")
            index_path = report_info.get("index_path")
            report_dir = os.path.dirname(index_path) if index_path else None
            generate_duration = report_info.get("generate_duration")
            error_msg = report_info.get("error_msg")

            try:
                db.upsert_history(
                    task_id=task_id,
                    device_id=device_id,
                    status=status,
                    end_time=generate_time,
                    report_index_path=index_path,
                    report_meta_path=meta_path,
                    report_generate_duration=generate_duration,
                    error_msg=error_msg,
                )
                imported += 1
            except Exception as e:
                log.error(f"导入任务{task_id}历史失败：{str(e)}", exc_info=True)
                skipped += 1

        return jsonify(
            {
                "code": 200,
                "msg": f"历史报告导入完成，成功{imported}条，跳过{skipped}条",
                "data": {"imported": imported, "skipped": skipped},
            }
        )
    except Exception as e:
        error_msg = f"导入历史报告到SQLite失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.get("/exec-set/history")
def get_exec_set_history_list():
    """
    获取执行集主任务的执行历史列表。
    支持通过query参数exec_set_id过滤指定执行集，limit控制返回数量。
    """
    exec_set_id = request.args.get("exec_set_id") or None

    # 兼容：limit 模式（返回 list）
    if request.args.get("limit") is not None and request.args.get("page") is None:
        try:
            limit = int(request.args.get("limit", 100))
            if limit <= 0:
                limit = 100
        except Exception:
            limit = 100
        try:
            histories = db.list_exec_set_histories(exec_set_id=exec_set_id, limit=limit)
            return jsonify(
                {
                    "code": 200,
                    "msg": f"获取执行集执行历史成功（共{len(histories)}条）",
                    "data": histories,
                }
            )
        except Exception as e:
            error_msg = f"获取执行集执行历史失败：{str(e)}"
            log.error(error_msg, exc_info=True)
            return jsonify({"code": 400, "msg": error_msg, "data": []})

    # 新逻辑：分页
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10))
    except Exception:
        page = 1
        page_size = 10
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    try:
        total = db.count_exec_set_histories(exec_set_id=exec_set_id)
        items = db.list_exec_set_histories_paginated(
            exec_set_id=exec_set_id, offset=offset, limit=page_size
        )
        total_pages = max((total + page_size - 1) // page_size, 1)
        return jsonify(
            {
                "code": 200,
                "msg": "获取执行集执行历史成功",
                "data": {
                    "items": items,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "exec_set_id": exec_set_id,
                },
            }
        )
    except Exception as e:
        error_msg = f"获取执行集执行历史失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify(
            {"code": 400, "msg": error_msg, "data": {"items": [], "total": 0}}
        )


@test_bp.get("/exec-set/history/<main_task_id>")
def get_exec_set_history_detail_api(main_task_id: str):
    """
    获取某次执行集任务的主任务+子任务执行历史明细。
    """
    try:
        detail = db.get_exec_set_history_detail(main_task_id)
        if not detail:
            return jsonify(
                {"code": 404, "msg": f"执行集主任务{main_task_id}无历史记录", "data": None}
            )

        return jsonify(
            {
                "code": 200,
                "msg": "获取执行集执行历史明细成功",
                "data": detail,
            }
        )
    except Exception as e:
        error_msg = f"获取执行集主任务{main_task_id}执行历史失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.get("/running")
def get_running_tasks():
    """获取所有运行中任务"""
    try:
        # 优先从数据库的运行时任务表中获取，包含 pending 与 running
        running_tasks = db.list_running_tasks()
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


@test_bp.get("/overview")
def get_overview_stats():
    """
    获取首页概览统计数据：
    - case_count: 可用测试用例数量
    - exec_set_count: 可用执行集数量
    - history_single_count: 已执行单用例任务数量
    - history_exec_set_count: 已执行执行集任务数量
    """
    try:
        case_count = len(db.list_cases())
        exec_set_count = db.count_exec_sets()
        history_single_count = db.count_histories_by_type(None)
        history_exec_set_count = db.count_histories_by_type("exec_set")
        return jsonify(
            {
                "code": 200,
                "msg": "获取概览统计成功",
                "data": {
                    "case_count": case_count,
                    "exec_set_count": exec_set_count,
                    "history_single_count": history_single_count,
                    "history_exec_set_count": history_exec_set_count,
                },
            }
        )
    except Exception as e:
        error_msg = f"获取概览统计失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.post("/stop/<task_id>")
def stop_test_task(task_id: str):
    """停止指定测试任务"""
    try:
        task = test_tasks.get(task_id)
        if not task:
            # 内存中已无任务信息时，尝试根据运行时任务表做“强制停止”
            runtime = db.get_task_runtime(task_id)
            if not runtime:
                return jsonify({
                    "code": 404,
                    "msg": f"任务{task_id}不存在",
                    "data": None
                })

            # 仅对标记为 pending/running 的任务做强制终止
            if runtime.get("status") not in ("pending", "running"):
                return jsonify({
                    "code": 400,
                    "msg": f"任务{task_id}不在运行中，状态：{runtime.get('status')}",
                    "data": None
                })

            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stop_reason = "用户手动强制停止（任务实例已不存在）"

            # 计算执行耗时（若有开始时间）
            exec_duration = None
            try:
                start_str = runtime.get("start_time")
                if start_str and end_time:
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                    exec_duration = max((end_dt - start_dt).total_seconds(), 0.0)
            except Exception:
                exec_duration = None

            try:
                # 更新运行时任务表状态
                db.upsert_task_runtime(
                    task_id=task_id,
                    status="stopped",
                    end_time=end_time,
                    stop_reason=stop_reason,
                )
                # 同步执行历史
                db.upsert_history(
                    task_id=task_id,
                    status="stop",
                    end_time=end_time,
                    exec_duration=exec_duration,
                    error_msg=stop_reason,
                )
            except Exception as e:
                log.error(f"强制停止任务{task_id}时更新数据库失败：{str(e)}", exc_info=True)

            log.info(f"任务{task_id}已被手动强制停止（仅更新数据库记录）")
            return jsonify({
                "code": 200,
                "msg": f"任务{task_id}已强制停止",
                "data": {"task_id": task_id}
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

        # 计算执行耗时（若有开始时间）
        exec_duration = None
        try:
            start_str = task.get("start_time")
            end_str = task.get("end_time")
            if start_str and end_str:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                exec_duration = max((end_dt - start_dt).total_seconds(), 0.0)
        except Exception:
            exec_duration = None

        try:
            db.upsert_history(
                task_id=task_id,
                status="stop",
                end_time=task["end_time"],
                exec_duration=exec_duration,
                error_msg=task["stop_reason"],
            )
            db.upsert_task_runtime(
                task_id=task_id,
                status="stopped",
                end_time=task["end_time"],
                stop_reason=task["stop_reason"],
            )
        except Exception as e:
            log.error(f"写入任务{task_id}停止历史失败：{str(e)}", exc_info=True)

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
    """获取单个测试用例内容（suite_id 直接为用例在 SQLite 中的 id）"""
    try:
        case = db.get_case(suite_id)
        if not case:
            return jsonify({"code": 404, "msg": "用例不存在", "data": None})

        return jsonify({
            "code": 200,
            "msg": "获取用例内容成功",
            "data": {
                "id": case["id"],
                "name": case["name"],
                "content": case.get("content"),
                "abs_path": case.get("file_name"),
                "rel_path": case.get("rel_path")
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

        if not name:
            return jsonify({"code": 400, "msg": "用例名称不能为空", "data": None})

        case = db.create_case(name=name, content=content)

        return jsonify({
            "code": 200,
            "msg": "用例创建成功",
            "data": {"id": case["id"], "name": case["name"]}
        })
    except Exception as e:
        error_msg = f"创建用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.put("/suite/<int:suite_id>")
def update_test_suite(suite_id):
    """更新测试用例内容（suite_id 直接为用例在 SQLite 中的 id）"""
    try:
        req_data = request.get_json() or {}
        content = req_data.get("content")

        if content is None:
            return jsonify({"code": 400, "msg": "请提供用例内容", "data": None})

        ok = db.update_case(suite_id, name=None, content=content)
        if not ok:
            return jsonify({"code": 404, "msg": "用例不存在", "data": None})

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
    """删除测试用例（suite_id 直接为用例在 SQLite 中的 id）"""
    try:
        ok = db.delete_case(suite_id)
        if not ok:
            return jsonify({"code": 404, "msg": "用例不存在", "data": None})

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
    """获取测试用例内容（suite_id 直接为 SQLite 中的用例 id）"""
    try:
        case = db.get_case(suite_id)
        if not case:
            return jsonify({"code": 404, "msg": "用例不存在", "data": None})

        content = case.get("content")
        return jsonify(
            {
                "code": 200,
                "msg": "获取用例内容成功",
                "data": {
                    "content": content,
                    "path": case.get("name"),
                },
            }
        )
    except Exception as e:
        error_msg = f"获取用例内容失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


@test_bp.put("/suites/<int:suite_id>")
def update_suite(suite_id):
    """更新测试用例（suite_id 直接为 SQLite 中的用例 id）"""
    try:
        req_data = request.get_json() or {}
        new_name = req_data.get("name")
        new_content = req_data.get("content")

        if not new_name or new_content is None:
            return jsonify({"code": 400, "msg": "名称和内容不能为空", "data": None})

        ok = db.update_case(suite_id, name=new_name, content=new_content)
        if not ok:
            return jsonify({"code": 404, "msg": "用例不存在", "data": None})

        log.info(f"用例{suite_id}更新成功（名称与内容已更新）")
        return jsonify({"code": 200, "msg": "用例更新成功", "data": None})
    except Exception as e:
        error_msg = f"更新用例失败：{str(e)}"
        log.error(error_msg)
        return jsonify({"code": 400, "msg": error_msg, "data": None})


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


@test_bp.post("/validate-code")
def validate_code():
    """Python 语法校验接口，仅做语法检查，不执行代码"""
    try:
        req_data = request.get_json() or {}
        code = req_data.get("code", "")

        # 空代码直接视为通过
        if not code.strip():
            return jsonify(
                {
                    "code": 200,
                    "msg": "代码为空，跳过语法校验",
                    "data": {"valid": True, "errors": []},
                }
            )

        import ast

        try:
            ast.parse(code)
        except SyntaxError as se:
            error_detail = {
                "lineno": se.lineno,
                "offset": se.offset,
                "text": se.text,
                "msg": se.msg,
            }
            return jsonify(
                {
                    "code": 400,
                    "msg": "语法校验失败",
                    "data": {"valid": False, "errors": [error_detail]},
                }
            )

        return jsonify(
            {
                "code": 200,
                "msg": "语法校验通过",
                "data": {"valid": True, "errors": []},
            }
        )
    except Exception as e:
        error_msg = f"语法校验异常：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify(
            {"code": 500, "msg": error_msg, "data": {"valid": False, "errors": []}}
        )

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
                    "suite_id": s["id"],  # 这里的suite_id即为case_id
                    "abs_path": s.get("abs_path"),
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

        test_suite_dir = current_app.config["TEST_SUITE_DIR"]
        ensure_dir_exists(test_suite_dir)

        # 4. 批量创建子任务（每个用例一个子任务）
        for case in exec_set["cases"]:
            # 从SQLite获取用例内容，并为每个子任务生成独立的临时.py文件
            case_id = case["case_id"]
            case_detail = db.get_case(case_id)
            if not case_detail:
                log.warning(f"执行集{exec_set_id}中的用例{case_id}在数据库中不存在，跳过")
                continue

            file_name = case_detail.get("file_name") or f"case_{case_id}.py"
            suite_abs_path = safe_join(test_suite_dir, f"{main_task_id}_{file_name}")
            with open(suite_abs_path, "w", encoding="utf-8") as f:
                f.write(case_detail["content"])

            sub_task_id = get_task_id()
            test_tasks[sub_task_id] = {
                "task_id": sub_task_id,
                "main_task_id": main_task_id,
                "device_id": device_id,
                "suite_info": {"id": case_id, "name": case_detail["name"], "abs_path": suite_abs_path},
                "status": "pending",
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # 写入执行历史与运行时任务（子任务）
            try:
                db.upsert_history(
                    task_id=sub_task_id,
                    main_task_id=main_task_id,
                    type_="single",
                    device_id=device_id,
                    case_id=case_id,
                    exec_set_id=exec_set_id,
                    status="pending",
                    create_time=test_tasks[sub_task_id]["create_time"],
                )
                db.upsert_task_runtime(
                    task_id=sub_task_id,
                    main_task_id=main_task_id,
                    type_="single",
                    device_id=device_id,
                    status="pending",
                    create_time=test_tasks[sub_task_id]["create_time"],
                )
            except Exception as e:
                log.error(f"写入子任务{sub_task_id}初始历史失败：{str(e)}", exc_info=True)

            # 后台启动子任务
            Thread(
                target=run_task_background,
                args=(sub_task_id, device_id, suite_abs_path),
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

        # 主任务历史与运行时任务
        try:
            db.upsert_history(
                task_id=main_task_id,
                type_="exec_set",
                device_id=device_id,
                exec_set_id=exec_set_id,
                status="running",
                create_time=test_tasks[main_task_id]["start_time"],
            )
            db.upsert_task_runtime(
                task_id=main_task_id,
                main_task_id=None,
                type_="exec_set",
                device_id=device_id,
                status="running",
                create_time=test_tasks[main_task_id]["start_time"],
                start_time=test_tasks[main_task_id]["start_time"],
            )
        except Exception as e:
            log.error(f"写入执行集主任务{main_task_id}初始历史失败：{str(e)}", exc_info=True)

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