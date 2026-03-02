# ums_uiautomator/app/routes/exec_set.py
# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import datetime
from flask import Blueprint, request, jsonify
from core.exec_set_manager import ExecSetManager
from util.log_util import LogUtil

exec_set_bp = Blueprint("exec_set", __name__, url_prefix="/exec_sets")
logger = LogUtil(logger_name="exec_set_api")
exec_set_manager = ExecSetManager()


@exec_set_bp.get("/")
def get_all_exec_sets():
    """查询所有执行集"""
    try:
        exec_sets = exec_set_manager.get_all_exec_sets()
        return jsonify({
            "code": 200,
            "msg": "查询成功",
            "data": exec_sets
        })
    except Exception as e:
        logger.error(f"查询所有执行集失败：{str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"查询失败：{str(e)}",
            "data": None
        })


@exec_set_bp.get("/<int:exec_set_id>")
def get_exec_set(exec_set_id):
    """查询单个执行集"""
    try:
        exec_set = exec_set_manager.get_exec_set_by_id(exec_set_id)
        if not exec_set:
            return jsonify({
                "code": 404,
                "msg": f"执行集ID{exec_set_id}不存在",
                "data": None
            })
        return jsonify({
            "code": 200,
            "msg": "查询成功",
            "data": exec_set
        })
    except Exception as e:
        logger.error(f"查询执行集失败：ID={exec_set_id}，错误={str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"查询失败：{str(e)}",
            "data": None
        })


@exec_set_bp.post("/")
def add_exec_set():
    """新增执行集"""
    try:
        req_data = request.get_json() or {}
        # 校验参数
        if not req_data.get("name"):
            return jsonify({
                "code": 400,
                "msg": "执行集名称不能为空",
                "data": None
            })

        # 构造执行集数据
        exec_set_data = {
            "name": req_data.get("name"),
            "case_ids": req_data.get("case_ids", []),
            "desc": req_data.get("desc", ""),
            "create_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 新增执行集
        new_id = exec_set_manager.add_exec_set(exec_set_data)
        return jsonify({
            "code": 200,
            "msg": "新增成功",
            "data": {"id": new_id}
        })
    except Exception as e:
        logger.error(f"新增执行集失败：{str(e)}，请求数据={req_data}")
        return jsonify({
            "code": 500,
            "msg": f"新增失败：{str(e)}",
            "data": None
        })


@exec_set_bp.put("/<int:exec_set_id>")
def update_exec_set(exec_set_id):
    """修改执行集"""
    try:
        req_data = request.get_json() or {}
        # 校验执行集是否存在
        if not exec_set_manager.get_exec_set_by_id(exec_set_id):
            return jsonify({
                "code": 404,
                "msg": f"执行集ID{exec_set_id}不存在",
                "data": None
            })

        # 构造更新数据
        update_data = {}
        if "name" in req_data:
            update_data["name"] = req_data["name"]
        if "case_ids" in req_data:
            update_data["case_ids"] = req_data["case_ids"]
        if "desc" in req_data:
            update_data["desc"] = req_data["desc"]
        update_data["update_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新执行集
        success = exec_set_manager.update_exec_set(exec_set_id, update_data)
        if success:
            return jsonify({
                "code": 200,
                "msg": "修改成功",
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "修改失败",
                "data": None
            })
    except Exception as e:
        logger.error(f"修改执行集失败：ID={exec_set_id}，错误={str(e)}，请求数据={req_data}")
        return jsonify({
            "code": 500,
            "msg": f"修改失败：{str(e)}",
            "data": None
        })


@exec_set_bp.delete("/<int:exec_set_id>")
def delete_exec_set(exec_set_id):
    """删除执行集"""
    try:
        # 校验执行集是否存在
        if not exec_set_manager.get_exec_set_by_id(exec_set_id):
            return jsonify({
                "code": 404,
                "msg": f"执行集ID{exec_set_id}不存在",
                "data": None
            })

        # 删除执行集
        success = exec_set_manager.delete_exec_set(exec_set_id)
        if success:
            return jsonify({
                "code": 200,
                "msg": "删除成功",
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "删除失败",
                "data": None
            })
    except Exception as e:
        logger.error(f"删除执行集失败：ID={exec_set_id}，错误={str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"删除失败：{str(e)}",
            "data": None
        })


@exec_set_bp.post("/<int:exec_set_id>/add_cases")
def add_cases_to_exec_set(exec_set_id):
    """给执行集添加用例"""
    try:
        req_data = request.get_json() or {}
        case_ids = req_data.get("case_ids", [])

        if not isinstance(case_ids, list) or not case_ids:
            return jsonify({
                "code": 400,
                "msg": "用例ID列表不能为空且必须是数组",
                "data": None
            })

        # 添加用例到执行集
        success = exec_set_manager.add_cases_to_exec_set(exec_set_id, case_ids)
        if success:
            return jsonify({
                "code": 200,
                "msg": "添加用例成功",
                "data": None
            })
        else:
            return jsonify({
                "code": 404,
                "msg": f"执行集ID{exec_set_id}不存在",
                "data": None
            })
    except Exception as e:
        logger.error(f"执行集添加用例失败：ID={exec_set_id}，用例IDs={case_ids}，错误={str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"添加用例失败：{str(e)}",
            "data": None
        })