# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
from flask import Blueprint, jsonify, send_from_directory, abort
from app.routes.test import test_tasks
from util.path_util import safe_join

report_bp = Blueprint("report", __name__)


@report_bp.get("/<task_id>")
def get_report_info(task_id: str):
    """获取报告基本信息（含访问URL）"""
    task = test_tasks.get(task_id)
    if not task or "report_path" not in task:
        return jsonify({
            "code": 404,
            "msg": f"任务{task_id}报告不存在（任务未完成或执行失败）",
            "data": None
        })

    return jsonify({
        "code": 200,
        "msg": "获取报告信息成功",
        "data": {
            "task_id": task_id,
            "report_path": task["report_path"],
            "log_path": task.get("log_path"),
            "access_url": f"/api/report/files/{task_id}/index.html",
            "pytest_returncode": task.get("pytest_returncode")
        }
    })


@report_bp.get("/files/<task_id>/<path:filename>")
def get_report_file(task_id: str, filename: str):
    """获取报告静态文件（兼容历史任务）"""
    import json  # 需导入json模块
    from util.path_util import get_report_root  # 假设存在获取报告根目录的工具函数
    import os

    # 1. 先从内存任务中查找
    task = test_tasks.get(task_id)

    # 2. 内存中不存在时，从文件系统加载报告元数据
    if not task or "report_path" not in task:
        # 构造report_meta.json路径（根据实际项目的报告存储结构）
        report_meta_path = os.path.join(
            get_report_root(),  # 替换为实际的报告根目录（如"ums_uiautomator/result"）
            task_id,
            "report_meta.json"
        )
        if not os.path.exists(report_meta_path):
            abort(404, description=f"任务{task_id}报告不存在")

        # 从元数据文件中读取report_path
        with open(report_meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
            # 提取报告目录（index.html所在的文件夹）
            report_dir = os.path.dirname(meta_data["report_info"]["index_path"])
            task = {"report_path": report_dir}  # 构造临时task对象

    # 3. 后续逻辑保持不变（安全拼接路径并返回文件）
    report_dir = task["report_path"]
    try:
        file_path = safe_join(report_dir, filename)
    except ValueError:
        abort(403, description="非法文件访问（路径穿越）")

    if not file_path or not os.path.exists(file_path):
        abort(404, description=f"报告文件不存在：{filename}")

    if filename.endswith('.html'):
        return send_from_directory(report_dir, filename, as_attachment=False, mimetype='text/html')

    return send_from_directory(report_dir, filename, as_attachment=False)