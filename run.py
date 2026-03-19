# -*- coding: utf-8 -*-
import os
import sys  # 必须最先导入 sys 模块

# Windows 控制台中文乱码兜底：尽量强制 Python stdout/stderr 为 UTF-8
# 注意：这只能解决“Python 输出编码”，若终端本身 codepage 非 UTF-8，仍建议在终端执行 `chcp 65001`
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # 避免在某些打包/重定向场景下抛异常影响启动
    pass

# 在打包后的环境中，确保当前工作目录是可执行文件所在目录
if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)

# 第一步：冻结模式下避免“dist 目录旧文件”影子覆盖
# - frozen(onefile/onedir)：优先使用 PyInstaller 解包目录 _MEIPASS（若存在）
# - frozen：不要把 dist/ 根目录硬塞到 sys.path，避免导入到旧的 util/core/conf 源码
# - 开发模式：按原逻辑把项目根目录加入 sys.path
if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    exe_dir_abs = os.path.abspath(exe_dir)
    disk_has_util = os.path.exists(os.path.join(exe_dir, "util", "path_util.py"))
    disk_has_core_pkg = os.path.exists(os.path.join(exe_dir, "core", "__init__.py"))
    # 仅当磁盘上存在旧的 util/core 源码包时，才移除 exe_dir 避免影子覆盖
    if disk_has_util or disk_has_core_pkg:
        sys.path = [
            p
            for p in sys.path
            if p not in ("", None) and os.path.abspath(p) != exe_dir_abs
        ]
    _meipass = getattr(sys, "_MEIPASS", None)
    if _meipass and _meipass not in sys.path:
        sys.path.insert(0, _meipass)
else:
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
