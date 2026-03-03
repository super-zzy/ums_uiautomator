# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
import traceback
import uuid
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
from threading import Thread
from core.test_executor import TestExecutor
from core.device_manager import DeviceManager
from util.log_util import LogUtil
from util.path_util import safe_join
from core.exec_set_manager import ExecSetManager

test_bp = Blueprint("test", __name__)
test_tasks = {}  # 全局任务状态缓存（task_id: 任务信息）

log = LogUtil("test", task_id=None).logger


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
            return jsonify({
                "code": 404,
                "msg": f"任务{task_id}不存在",
                "data": None
            })

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
    为执行集添加测试用例
    :param exec_set_id: 执行集ID
    :return: JSON响应
    """
    try:
        # 接收请求参数（示例：用例ID列表）
        data = request.get_json()
        case_ids = data.get("case_ids", [])

        if not case_ids:
            return jsonify({"code": 400, "msg": "用例ID列表不能为空"}), 400

        # 调用核心层方法处理exec_sets.json
        ExecSetManager.add_exec_set(exec_set_id, case_ids)

        return jsonify({"code": 200, "msg": "用例添加成功", "data": {"exec_set_id": exec_set_id}}), 200

    except FileNotFoundError:
        log.error(f"执行集配置文件exec_sets.json不存在")
        return jsonify({"code": 500, "msg": "执行集配置文件不存在"}), 500
    except Exception as e:
        log.error(f"添加用例到执行集失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"添加失败：{str(e)}"}), 500


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

        log.info(f"执行集任务{main_task_id}启动成功（设备：{device_id}，执行集：{exec_set['name']}，用例数：{len(sub_tasks)}）")
        return jsonify({
            "code": 200,
            "msg": "执行集测试任务已启动",
            "data": {"main_task_id": main_task_id, "sub_task_count": len(sub_tasks)}
        })
    except Exception as e:
        error_msg = f"启动执行集测试失败：{str(e)}"
        log.error(error_msg, exc_info=True)
        return jsonify({"code": 400, "msg": error_msg, "data": None})

    # ums_uiautomator/app/routes/test.py
    # 新增导入
    from core.test_executor import TestExecutor
    from core.exec_set_manager import ExecSetManager
    from conf import GlobalConfig

    # 新增执行集测试执行接口
    @test_bp.post("/exec_sets/<int:exec_set_id>/run")
    def run_exec_set_test(exec_set_id):
        """执行执行集自动化测试"""
        try:
            # 获取请求参数
            req_data = request.get_json() or {}
            device_id = req_data.get("device_id")
            task_id = req_data.get("task_id", f"exec_set_{exec_set_id}_{int(time.time())}")

            if not device_id:
                return jsonify({
                    "code": 400,
                    "msg": "device_id不能为空",
                    "data": None
                })

            # 校验执行集是否存在
            exec_set_manager = ExecSetManager()
            exec_set = exec_set_manager.get_exec_set_by_id(exec_set_id)
            if not exec_set:
                return jsonify({
                    "code": 404,
                    "msg": f"执行集ID{exec_set_id}不存在",
                    "data": None
                })

            # 初始化执行器（用例路径先传空，后续在run_exec_set中动态替换）
            # 注意：此处suite_abs_path传空，需确保prepare方法兼容，或调整prepare逻辑
            test_executor = TestExecutor(
                task_id=task_id,
                device_id=device_id,
                suite_abs_path=""  # 执行集模式下，用例路径动态获取
            )

            # 执行执行集测试
            result = test_executor.run_exec_set(exec_set_id)

            return jsonify({
                "code": 200,
                "msg": "执行集测试启动成功",
                "data": {
                    "task_id": task_id,
                    "exec_set_id": exec_set_id,
                    "exec_set_name": exec_set.get("name"),
                    "report_path": result.get("allure_report_path"),
                    "summary": result
                }
            })
        except Exception as e:
            log.error(f"执行集测试执行失败：ID={exec_set_id}，错误={str(e)}")
            return jsonify({
                "code": 500,
                "msg": f"执行失败：{str(e)}",
                "data": None
            })