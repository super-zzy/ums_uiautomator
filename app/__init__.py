# -*- coding: utf-8 -*-
import os
import sys
from flask import Flask, render_template  # 新增：导入 render_template 用于渲染模板
from flask_apscheduler import APScheduler

# 修正：动态获取项目根目录（兼容开发和打包环境）
if getattr(sys, 'frozen', False):
    # 打包后的环境（可执行文件运行时）
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    # 开发环境（通过 run.py 启动时）
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 检查项目根目录是否在 sys.path 中
if PROJECT_ROOT not in sys.path:
    # 自动添加根目录到 sys.path（避免手动启动的问题）
    sys.path.insert(0, PROJECT_ROOT)
    # 注释掉强制报错的逻辑，改为警告
    import logging
    logging.warning(
        f"项目根目录 {PROJECT_ROOT} 未加入 sys.path，已自动添加！\n"
        "建议通过项目根目录的 run.py 启动。"
    )

# 导入配置
from conf import GlobalConfig


def create_app():
    # 初始化 Flask 应用（指定模板文件夹路径，确保能找到 templates/index.html）
    app = Flask(
        __name__,
        template_folder="templates",  # 明确指定模板文件夹（app/templates）
        static_folder="static"  # 静态文件文件夹（可选，用于存放CSS/JS/图片）
    )

    # 配置应用
    app.config["TEST_SUITE_DIR"] = GlobalConfig["path"]["test_suite_dir"]
    app.config["REPORT_ROOT_DIR"] = GlobalConfig["path"]["report_root_dir"]
    app.config["SCHEDULER_API_ENABLED"] = False

    # 初始化 APScheduler
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()
    app.config["SCHEDULER"] = scheduler

    # 注册路由蓝图
    from app.routes.device import device_bp
    from app.routes.test import test_bp
    from app.routes.report import report_bp

    app.register_blueprint(device_bp, url_prefix="/api/device")
    app.register_blueprint(test_bp, url_prefix="/api/test")
    app.register_blueprint(report_bp, url_prefix="/api/report")

    # 修复：首页路由指向 templates/index.html（使用 render_template 渲染）
    @app.route("/")
    def index():
        # 渲染模板文件（自动从 app/templates 文件夹查找 index.html）
        return render_template("index.html")

    return app
