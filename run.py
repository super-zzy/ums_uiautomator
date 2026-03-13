# -*- coding: utf-8 -*-
import os
import sys  # 必须最先导入 sys 模块

# 在打包后的环境中，确保当前工作目录是可执行文件所在目录
if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)

# 第一步：强制将项目根目录加入 sys.path（重中之重！）
# 作用：确保后续导入 app 时，app/__init__.py 能找到上层的 conf 模块
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))  # 获取 run.py 所在目录（项目根目录）
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)  # 插入到 sys.path 最前面，优先加载
    print(f"[DEBUG] 已将项目根目录加入 sys.path：{PROJECT_ROOT}")

# 第二步：此时再导入 app 和 conf（顺序不能错！）
from app import create_app
from conf import GlobalConfig
from util.log_util import TempLog

log = TempLog()

if __name__ == "__main__":
    try:
        # 创建 Flask 应用
        app = create_app()
        log.info(f"Flask应用初始化完成（环境：{GlobalConfig['env']}）")

        # 启动 Web 服务
        host = GlobalConfig["web"]["host"]
        port = GlobalConfig["web"]["port"]
        debug = GlobalConfig["web"]["debug"]

        log.info(f"启动Web服务：http://{host}:{port}")
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    except Exception as e:
        log.error(f"项目启动失败：{str(e)}", exc_info=True)
        raise
