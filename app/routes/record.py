# @Time     : 2026/3/17
# @Author   : zyli3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import textwrap
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from xml.etree import ElementTree as ET
import subprocess

from flask import Blueprint, jsonify, request, send_file

from core.device_manager import DeviceManager
from util.log_util import TempLog
from conf import GlobalConfig


record_bp = Blueprint("record", __name__)
log = TempLog()


# 简单的内存录制会话管理（按 device_id 维度，只支持单人使用场景）
_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_session(device_id: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(device_id)
    if not sess:
        sess = {
            "device_id": device_id,
            "start_time": _now_str(),
            "actions": [],  # type: List[Dict[str, Any]]
        }
        _SESSIONS[device_id] = sess
    return sess


def _parse_bounds(bounds: str) -> Optional[Tuple[int, int, int, int]]:
    """
    解析 Android UI 层级中的 bounds 字符串：[x1,y1][x2,y2]
    返回 (x1, y1, x2, y2)
    """
    if not bounds:
        return None
    try:
        # 形如 "[0,72][1080,1794]"
        parts = bounds.replace("[", "").split("]")
        p1 = parts[0]
        p2 = parts[1]
        x1_str, y1_str = p1.split(",")
        x2_str, y2_str = p2.split(",")
        return int(x1_str), int(y1_str), int(x2_str), int(y2_str)
    except Exception:
        return None


def _find_element_by_point(dev, x: int, y: int) -> Optional[Dict[str, Any]]:
    """
    基于 dump_hierarchy 的 XML，找到包含给定坐标 (x, y) 的最小节点。
    返回包含常用属性的字典，用于生成更直观的定位表达式。
    """
    try:
        xml_str = dev.dump_hierarchy()
    except Exception as e:
        log.warning(f"dump_hierarchy 失败，无法获取元素信息：{e}")
        return None

    try:
        root = ET.fromstring(xml_str)
    except Exception as e:
        log.warning(f"解析层级 XML 失败：{e}")
        return None

    best_node = None
    best_area = None

    for node in root.iter():
        bounds = node.attrib.get("bounds") or node.attrib.get("bounds".upper())
        rect = _parse_bounds(bounds)
        if not rect:
            continue
        x1, y1, x2, y2 = rect
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            continue
        area = max(1, (x2 - x1) * (y2 - y1))
        if best_area is None or area < best_area:
            best_area = area
            best_node = (node, rect)

    if not best_node:
        return None

    node, rect = best_node
    x1, y1, x2, y2 = rect
    info: Dict[str, Any] = {
        "resource_id": node.attrib.get("resource-id") or "",
        "text": node.attrib.get("text") or "",
        "content_desc": node.attrib.get("content-desc") or "",
        "class_name": node.attrib.get("class") or "",
        "package": node.attrib.get("package") or "",
        "bounds": f"[{x1},{y1}][{x2},{y2}]",
    }
    return info


def _build_locator_expr(elem: Dict[str, Any]) -> Optional[str]:
    """
    根据元素属性生成 uiautomator2 推荐定位表达式（不带 .click()），优先级：
    1. resourceId + text
    2. resourceId
    3. text
    4. contentDescription
    若都没有，则返回 None，后续回退到坐标点击。
    """
    if not elem:
        return None

    rid = elem.get("resource_id") or ""
    text = elem.get("text") or ""
    desc = elem.get("content_desc") or ""

    parts = []
    if rid:
        parts.append(f'resourceId="{rid}"')
    if text:
        parts.append(f'text="{text}"')

    if parts:
        return f'd({", ".join(parts)})'

    if desc:
        return f'd(description="{desc}")'

    return None


@record_bp.post("/start")
def start_record():
    """开始录制：仅在内存中初始化会话"""
    data = request.get_json() or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})

    try:
        # 确保设备可用（会触发 uiautomator2 初始化）
        DeviceManager.get_uiautomator_instance(device_id, task_id="record")
    except Exception as e:
        log.error(f"录制开始失败，设备{device_id}初始化异常：{e}", exc_info=True)
        return jsonify(
            {"code": 500, "msg": f"设备初始化失败：{e}", "data": None}
        )

    sess = _ensure_session(device_id)
    sess["start_time"] = _now_str()
    sess["actions"] = []

    log.info(f"录制会话开始：device_id={device_id}")
    return jsonify(
        {
            "code": 200,
            "msg": "录制已开始",
            "data": {"device_id": device_id, "start_time": sess["start_time"]},
        }
    )


@record_bp.post("/click")
def record_click():
    """
    记录一次点击事件，并立即在设备上执行点击。
    请求体：
    {
        "device_id": "xxx",
        "x": 100,
        "y": 200
    }
    """
    data = request.get_json() or {}
    device_id = data.get("device_id")
    x = data.get("x")
    y = data.get("y")

    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})
    if x is None or y is None:
        return jsonify({"code": 400, "msg": "请提供 x 和 y 坐标", "data": None})

    try:
        x_int = int(x)
        y_int = int(y)
    except (TypeError, ValueError):
        return jsonify({"code": 400, "msg": "x 和 y 必须为整数", "data": None})

    try:
        dev = DeviceManager.get_uiautomator_instance(device_id, task_id="record")
        # 直接调用 uiautomator2 的 click，确保与实际执行一致
        dev.click(x_int, y_int)

        # 通过层级信息反查当前坐标对应的元素属性（可能失败，失败时仅记录坐标）
        elem_info = _find_element_by_point(dev, x_int, y_int)
        if elem_info:
            locator = _build_locator_expr(elem_info)
            if locator:
                elem_info["locator"] = locator
    except Exception as e:
        log.error(
            f"录制点击执行失败：device={device_id}, x={x_int}, y={y_int}, err={e}",
            exc_info=True,
        )
        return jsonify({"code": 500, "msg": f"执行点击失败：{e}", "data": None})

    sess = _ensure_session(device_id)
    action = {
        "type": "click",
        "x": x_int,
        "y": y_int,
        "time": _now_str(),
    }
    if elem_info:
        action["element"] = elem_info

    sess["actions"].append(action)

    return jsonify({"code": 200, "msg": "点击已记录", "data": action})


@record_bp.post("/swipe")
def record_swipe():
    """
    记录一次滑动操作（如下拉、上滑等），并在设备上实际执行。
    请求体：
    {
        "device_id": "xxx",
        "start_x": 100,
        "start_y": 1600,
        "end_x": 100,
        "end_y": 400
    }
    """
    data = request.get_json() or {}
    device_id = data.get("device_id")
    sx = data.get("start_x")
    sy = data.get("start_y")
    ex = data.get("end_x")
    ey = data.get("end_y")

    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})
    if None in (sx, sy, ex, ey):
        return jsonify(
            {"code": 400, "msg": "请提供 start_x/start_y/end_x/end_y", "data": None}
        )

    try:
        sx_i = int(sx)
        sy_i = int(sy)
        ex_i = int(ex)
        ey_i = int(ey)
    except (TypeError, ValueError):
        return jsonify(
            {
                "code": 400,
                "msg": "start_x/start_y/end_x/end_y 必须为整数",
                "data": None,
            }
        )

    try:
        # 使用 ADB shell input swipe 执行滑动，避免部分系统上 uiautomator2 swipe 的权限限制
        duration_ms = 300
        cmd = [
            GlobalConfig["device"]["adb_path"],
            "-s",
            device_id,
            "shell",
            "input",
            "swipe",
            str(sx_i),
            str(sy_i),
            str(ex_i),
            str(ey_i),
            str(duration_ms),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "adb swipe 执行失败")
    except Exception as e:
        log.error(
            f"录制滑动执行失败：device={device_id}, "
            f"({sx_i},{sy_i})->({ex_i},{ey_i}), err={e}",
            exc_info=True,
        )
        return jsonify({"code": 500, "msg": f"执行滑动失败：{e}", "data": None})

    sess = _ensure_session(device_id)
    action = {
        "type": "swipe",
        "start_x": sx_i,
        "start_y": sy_i,
        "end_x": ex_i,
        "end_y": ey_i,
        "time": _now_str(),
    }
    sess["actions"].append(action)

    return jsonify({"code": 200, "msg": "滑动已记录", "data": action})


@record_bp.get("/screenshot")
def get_screenshot():
    """
    获取当前屏幕截图（PNG）。
    查询参数：device_id=xxx
    """
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})

    try:
        dev = DeviceManager.get_uiautomator_instance(device_id, task_id="record")
        # uiautomator2 screenshot：返回 PIL.Image
        img = dev.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(
            buf,
            mimetype="image/png",
            as_attachment=False,
        )
    except Exception as e:
        log.error(f"获取截图失败：device={device_id}, err={e}", exc_info=True)
        return jsonify({"code": 500, "msg": f"获取截图失败：{e}", "data": None})


@record_bp.get("/device-info")
def get_device_info():
    """
    获取录制所需的设备信息，例如屏幕分辨率。
    查询参数：device_id=xxx
    """
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})

    try:
        dev = DeviceManager.get_uiautomator_instance(device_id, task_id="record")
        width, height = dev.window_size()
        return jsonify(
            {
                "code": 200,
                "msg": "获取设备信息成功",
                "data": {"device_id": device_id, "width": width, "height": height},
            }
        )
    except Exception as e:
        log.error(f"获取设备信息失败：device={device_id}, err={e}", exc_info=True)
        return jsonify({"code": 500, "msg": f"获取设备信息失败：{e}", "data": None})


def _generate_python_code(device_id: str, actions: List[Dict[str, Any]]) -> str:
    """
    根据录制的动作生成 Python 脚本。
    简单示例：按顺序重放点击动作。
    """
    body_lines: List[str] = []
    last_time = None
    for act in actions:
        act_type = act.get("type")
        if act_type not in ("click", "swipe"):
            continue

        # 简单按顺序插入时间间隔（秒）
        cur_time_str = act.get("time")
        if last_time and cur_time_str:
            try:
                dt1 = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                dt2 = datetime.strptime(cur_time_str, "%Y-%m-%d %H:%M:%S")
                delta = max((dt2 - dt1).total_seconds(), 0.0)
                if delta >= 0.2:
                    body_lines.append(f"time.sleep({round(delta, 1)})")
            except Exception:
                # 忽略时间解析错误
                pass

        if act_type == "click":
            elem = act.get("element") or {}
            locator = _build_locator_expr(elem) if elem else None

            # 生成注释，帮助人工理解录制对象
            comment_parts = []
            if elem.get("text"):
                comment_parts.append(f"text='{elem['text']}'")
            if elem.get("resource_id"):
                comment_parts.append(f"resourceId='{elem['resource_id']}'")
            if elem.get("content_desc"):
                comment_parts.append(f"desc='{elem['content_desc']}'")
            if comment_parts:
                body_lines.append(f"# 点击元素（{', '.join(comment_parts)}）")

            if locator:
                body_lines.append(f"{locator}.click()")
            else:
                # 回退到坐标点击
                body_lines.append(f"d.click({act['x']}, {act['y']})")

        elif act_type == "swipe":
            sx = act.get("start_x")
            sy = act.get("start_y")
            ex = act.get("end_x")
            ey = act.get("end_y")
            if None not in (sx, sy, ex, ey):
                body_lines.append(
                    f"d.swipe({int(sx)}, {int(sy)}, {int(ex)}, {int(ey)}, 0.2)"
                )

        last_time = cur_time_str or last_time

    if not body_lines:
        body_lines.append("# TODO: 当前录制无任何可执行动作")

    code = f'''import uiautomator2 as u2
import time


def test_recorded_case(device_id="{device_id}"):
    """
    通过 UI 自动化平台录制生成的示例用例。
    可根据需要自行补充断言等逻辑。
    """
    d = u2.connect(device_id)
    d.healthcheck()  # 确保会话可用

    # 录制动作回放开始
{textwrap.indent("\n".join(body_lines), "    ")}
'''
    return code


@record_bp.post("/stop")
def stop_record():
    """
    停止录制，并返回生成的 Python 脚本内容（前端可在编辑器中展示与保存）。
    请求体：{"device_id": "xxx"}
    """
    data = request.get_json() or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"code": 400, "msg": "请指定 device_id", "data": None})

    sess = _SESSIONS.get(device_id)
    if not sess or not sess.get("actions"):
        return jsonify(
            {"code": 400, "msg": "当前设备暂无录制动作，请先进行录制操作", "data": None}
        )

    actions: List[Dict[str, Any]] = sess["actions"]
    code = _generate_python_code(device_id, actions)

    # 给一个默认用例名建议
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"record_{ts}.py"

    log.info(f"录制结束：device_id={device_id}, actions={len(actions)}")

    return jsonify(
        {
            "code": 200,
            "msg": "录制结束，已生成脚本",
            "data": {"suggest_name": default_name, "code": code},
        }
    )


