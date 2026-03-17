# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
"""
路由模块统一导出：
将各功能模块的蓝图集中在此导出，简化主应用的导入逻辑
"""

# 从各路由文件中导入蓝图对象
from app.routes.device import device_bp
from app.routes.test import test_bp
from app.routes.report import report_bp
from app.routes.record import record_bp

# 定义__all__，明确导出内容（可选，但符合Python规范）
__all__ = ["device_bp", "test_bp", "report_bp", "record_bp"]