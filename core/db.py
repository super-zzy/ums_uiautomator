import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from util.log_util import TempLog

log = TempLog()

HISTORY_STATUS_SUCCESS = "success"
HISTORY_STATUS_FAILURE = "failure"
HISTORY_STATUS_STOP = "stop"


def normalize_history_status(value: Optional[str]) -> Optional[str]:
    """
    将任意来源的状态归一化为三值枚举：
    - success
    - failure
    - stop

    对于 pending/running 等“非最终态”，返回 None（不写入 history.status），
    历史列表查询仅展示最终态记录。
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None

    if s in ("success", "passed", "pass", "ok") or s.startswith("success"):
        return HISTORY_STATUS_SUCCESS

    if (
        s in ("failed", "failure", "error", "exception")
        or s.startswith("failed")
        or s.startswith("failure")
        or "failed" in s
        or "failure" in s
        or "error" in s
        or "exception" in s
    ):
        return HISTORY_STATUS_FAILURE

    if (
        s in ("stopped", "stop", "stopping", "cancelled", "canceled", "killed")
        or s.startswith("stop")
        or "stopped" in s
    ):
        return HISTORY_STATUS_STOP

    # 非最终态：不写入 history.status（避免出现额外状态值）
    if s in ("pending", "running", "unknown"):
        return None

    # 兜底：不写入，避免污染枚举
    return None


if getattr(sys, "frozen", False):
    # 打包运行时：把数据落到 exe 所在目录，避免依赖 core 是否以“真实目录文件形式”存在
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "ums.sqlite3")

# uiautomator2 常用断言/校验思路（method_key 稳定，INSERT OR IGNORE 便于增量补充）
ASSERTION_METHOD_SEEDS: List[Tuple[str, str, str, str, Optional[str], int]] = [
    (
        "exists_basic",
        "控件存在 (exists)",
        "元素存在与等待",
        "立即判断当前层级是否存在匹配选择器的控件；为 True 时可视为页面已出现目标元素。",
        'assert d(text="确定").exists',
        10,
    ),
    (
        "exists_timeout",
        "限时内出现 (exists + timeout)",
        "元素存在与等待",
        "在指定秒数内轮询，超时前若出现则通过；适合网络或动画导致的延迟加载。",
        'assert d(text="加载完成").exists(timeout=10.0)',
        20,
    ),
    (
        "wait_gone",
        "等待消失 (wait_gone)",
        "元素存在与等待",
        "断言某控件在超时时间内从界面消失，例如等待加载圈或弹窗关闭。",
        'assert d(text="请稍候").wait_gone(timeout=15.0)',
        30,
    ),
    (
        "must_wait",
        "必须出现否则抛错 (must_wait)",
        "元素存在与等待",
        "与 wait 类似，未在超时内找到会抛异常，适合作为强前置条件。",
        'd(text="首页").must_wait(timeout=8.0)',
        40,
    ),
    (
        "text_exact",
        "完全匹配文本 (text=)",
        "文本与选择器",
        "按完整可见文本查找；用于按钮、标题等文案固定的控件。",
        'assert d(text="登录").exists',
        50,
    ),
    (
        "text_contains",
        "包含子串 (textContains)",
        "文本与选择器",
        "文案可能带前后缀或省略号时使用，比完全匹配更宽松。",
        'assert d(textContains="登录").exists',
        60,
    ),
    (
        "text_startswith",
        "前缀匹配 (textStartsWith)",
        "文本与选择器",
        "匹配以某字符串开头的可见文本。",
        'assert d(textStartsWith="您好").exists',
        70,
    ),
    (
        "text_matches",
        "正则匹配 (textMatches)",
        "文本与选择器",
        "用正则描述可变文案，注意转义与性能。",
        'assert d(textMatches=r".*成功.*").exists',
        80,
    ),
    (
        "resource_id",
        "资源 ID (resourceId / resourceIdMatches)",
        "资源与控件类型",
        "按布局中的 @+id/xxx 查找，比文案稳定，适合多语言或文案常改场景。",
        'assert d(resourceId="com.example:id/submit").exists',
        90,
    ),
    (
        "description",
        "无障碍描述 (description)",
        "资源与控件类型",
        "按 contentDescription 查找，常见于图标按钮。",
        'assert d(description="搜索").exists',
        100,
    ),
    (
        "class_name",
        "类名 (className)",
        "资源与控件类型",
        "按控件类型过滤，常与 text/resourceId 组合缩小范围。",
        'assert d(className="android.widget.Button", text="OK").exists',
        110,
    ),
    (
        "package_name",
        "包名 (packageName)",
        "资源与控件类型",
        "限定当前窗口所属应用，避免跨应用同名控件误匹配。",
        'assert d(packageName="com.android.settings").exists',
        120,
    ),
    (
        "index_nth",
        "同条件第 N 个 (index)",
        "资源与控件类型",
        "多个相同选择器时按出现顺序取下标（从 0 开始）。",
        'assert d(className="android.widget.TextView", index=2).exists',
        130,
    ),
    (
        "relative_right",
        "相对位置：右侧 (right)",
        "相对定位",
        "先定位锚点控件，再取其右侧相邻匹配项，用于列表或表单无稳定 id 时。",
        'assert d(text="用户名").right(className="android.widget.EditText").exists',
        140,
    ),
    (
        "relative_left",
        "相对位置：左侧 (left)",
        "相对定位",
        "取锚点控件左侧的匹配元素。",
        'assert d(text=":").left(className="android.widget.TextView").exists',
        150,
    ),
    (
        "relative_up_down",
        "相对位置：上/下 (up / down)",
        "相对定位",
        "在布局树中向上或向下关联查找相邻控件。",
        'assert d(text="金额").down(textContains="元").exists',
        160,
    ),
    (
        "child_selector",
        "父子层级 (child / children)",
        "相对定位",
        "在父容器下按子选择器过滤，适合列表项内部结构。",
        'assert d(resourceId="com.app:id/list").child(text="第二项").exists',
        170,
    ),
    (
        "sibling",
        "兄弟节点 (sibling)",
        "相对定位",
        "与同级其它控件组合定位。",
        'assert d(text="标签A").sibling(textContains="值").exists',
        180,
    ),
    (
        "xpath_exists",
        "XPath 存在",
        "XPath 与其它",
        "复杂层级或属性条件用 XPath 表达；存在即表示结构符合预期。",
        'assert d.xpath("//android.widget.Button[@text=\\"确定\\"]").exists',
        190,
    ),
    (
        "xpath_count",
        "XPath 数量",
        "XPath 与其它",
        "统计匹配节点数量，用于列表条数等校验（需用 xpath 返回集或循环）。",
        "cnt = len(d.xpath('//android.widget.TextView').all())\nassert cnt >= 3",
        200,
    ),
    (
        "get_text_eq",
        "文案内容相等 (get_text)",
        "属性与状态",
        "控件已存在时读取其 text 与期望值比较。",
        'assert d(resourceId="com.app:id/title").get_text() == "首页"',
        210,
    ),
    (
        "info_enabled",
        "是否可点击/可用 (info)",
        "属性与状态",
        "通过 info 字典读取 enabled、clickable 等，断言控件交互状态。",
        'assert d(text="提交").info.get("enabled") is True',
        220,
    ),
    (
        "info_checked_selected",
        "选中/勾选状态",
        "属性与状态",
        "对 CheckBox、Switch、Radio 等断言 checked 或 selected。",
        'assert d(text="记住我").info.get("checked") is True',
        230,
    ),
    (
        "centered_on_screen",
        "是否在屏幕范围内 (center)",
        "属性与状态",
        "结合 window_size 判断控件中心点是否落在可视区域，用于滚动后可见性。",
        "w, h = d.window_size()\n(x, y) = d(text=\"目标\").center()\nassert 0 <= x <= w and 0 <= y <= h",
        240,
    ),
    (
        "bounds_not_empty",
        "边界矩形有效",
        "属性与状态",
        "info 中的 bounds 非空且宽高大于 0，表示已布局且可能可见。",
        'b = d(text="标题").info.get("bounds", {})\nassert b.get("bottom", 0) > b.get("top", 0)',
        250,
    ),
    (
        "focused",
        "焦点在指定输入框",
        "属性与状态",
        "断言当前获得焦点的控件为预期 EditText。",
        'assert d(focused=True, className="android.widget.EditText").exists',
        260,
    ),
    (
        "app_current_package",
        "当前前台包名",
        "应用与包名",
        "校验已进入目标应用，防止误操作其它 App。",
        'assert d.app_current()["package"] == "com.example.app"',
        270,
    ),
    (
        "app_current_activity",
        "当前 Activity",
        "应用与包名",
        "断言界面栈顶 Activity 符合预期（部分 ROM 返回格式略有差异）。",
        'assert "MainActivity" in d.app_current().get("activity", "")',
        280,
    ),
    (
        "app_started",
        "应用已启动 (app_start)",
        "应用与包名",
        "启动应用后结合 app_current 或界面元素确认启动成功。",
        'd.app_start("com.example.app", stop=True)\nassert d(packageName="com.example.app").exists(timeout=10.0)',
        290,
    ),
    (
        "implicitly_wait",
        "全局隐式等待",
        "设备与环境",
        "设置后续查找的默认等待时间，减少每句 exists 传 timeout。",
        "d.implicitly_wait(5.0)\nassert d(text=\"慢接口结果\").exists",
        300,
    ),
    (
        "screen_on",
        "屏幕点亮状态",
        "设备与环境",
        "从设备 info 中断言屏幕是否亮起（需先保证 wakelock/自动息屏策略）。",
        'assert d.info.get("screenOn") is True',
        310,
    ),
    (
        "orientation",
        "屏幕方向",
        "设备与环境",
        "断言当前为横屏或竖屏（具体取值依赖 uiautomator2 版本与设备）。",
        'assert d.orientation in ("natural", "portrait", "landscape")',
        320,
    ),
    (
        "toast_watch",
        "Toast 文案（watcher / Toast 扩展）",
        "设备与环境",
        "短时 Toast 需配合 watch 或第三方扩展；断言出现过提示文案。",
        "# 视环境启用 Message 监控或轮询 last toast API（若已配置）",
        330,
    ),
    (
        "shell_prop",
        "Shell 属性断言",
        "设备与环境",
        "通过 d.shell 执行 getprop 等，断言系统版本、型号等环境条件。",
        'out = d.shell("getprop ro.build.version.release")[0]\nassert out.strip()',
        340,
    ),
    (
        "screenshot_file",
        "截图落盘成功",
        "设备与环境",
        "截图保存后检查文件存在或大小，作为用例步骤完成的旁证。",
        'path = "s.png"\nd.screenshot(path)\nimport os\nassert os.path.isfile(path)',
        350,
    ),
    (
        "click_exists",
        "存在则点击 (click_exists)",
        "交互结合断言",
        "仅当控件存在时点击，返回是否点击；可配合后续界面变化断言。",
        'assert d(text="允许").click_exists(timeout=3.0)',
        360,
    ),
    (
        "long_click_exists",
        "存在则长按",
        "交互结合断言",
        "长按菜单项等场景，存在则执行长按。",
        'assert d(text="更多").long_click_exists(timeout=2.0)',
        370,
    ),
    (
        "set_text_clear",
        "输入框清空与输入",
        "交互结合断言",
        "对 EditText 清空后 set_text，再断言 get_text 与输入一致。",
        'ed = d(className="android.widget.EditText")\ned.clear_text()\ned.set_text("abc")\nassert ed.get_text() == "abc"',
        380,
    ),
    (
        "scroll_to_text",
        "滚动直到出现 (scroll.to)",
        "列表与滚动",
        "在可滚动容器中滚动直至某文本进入可视区域，再断言 exists。",
        'd(scrollable=True).scroll.to(text="页底项")\nassert d(text="页底项").exists',
        390,
    ),
    (
        "fling_end",
        "快速滑动至边界",
        "列表与滚动",
        "fling 多次后断言底部元素或「没有更多」类文案出现。",
        's = d(scrollable=True)\nfor _ in range(5): s.fling.vert.forward()\nassert d(textContains="没有更多").exists',
        400,
    ),
    (
        "pinch_zoom",
        "缩放手势后状态",
        "列表与滚动",
        "地图/图片场景缩放后断言比例或特定控件出现（依业务而定）。",
        "# d().pinch_in() / pinch_out() 后接元素断言",
        410,
    ),
    (
        "watch_click",
        "监视弹窗并自动点掉",
        "设备与环境",
        "用 watcher 处理随机系统弹窗，再断言主流程元素；适合权限/广告弹窗。",
        'd.watcher("perm").when("允许").click()\nd.watcher.run()\nassert d(text="主页").exists',
        420,
    ),
    (
        "alarm_shell_ui",
        "非 UI 与 UI 组合",
        "设备与环境",
        "先 adb shell 改数据或触发广播，再用 UI 断言结果页面。",
        "# d.shell(...); assert d(text=\"成功\").exists(timeout=10.0)",
        430,
    ),
    (
        "pytest_assert",
        "pytest / assert 失败即用例失败",
        "编写说明",
        "uiautomator2 本身无独立 assert API；通常用 Python assert 或 pytest 断言，失败即标记用例失败。",
        'assert d(text="完成").exists, "未出现完成态"',
        440,
    ),
    (
        "not_exists",
        "不应出现某元素",
        "元素存在与等待",
        "断言敏感入口或错误页未出现（注意时序，必要时先 wait 再判）。",
        'assert not d(text="崩溃报告").exists(timeout=2.0)',
        450,
    ),
    (
        "multiple_and",
        "多条件同时满足 (链式与)",
        "文本与选择器",
        "同一选择器链上同时限定 text、resourceId 等，减少误匹配。",
        'assert d(resourceId="com.app:id/name", textContains="张").exists',
        460,
    ),
    (
        "open_quick_settings",
        "系统面板与返回",
        "设备与环境",
        "打开快速设置等系统 UI 后断言特定开关或文案可见。",
        'd.open_quick_settings()\nassert d(textContains="WLAN").exists',
        470,
    ),
]


def _seed_assertion_methods(conn: sqlite3.Connection) -> None:
    """预置断言方法目录；method_key 唯一，已存在则跳过（INSERT OR IGNORE）。"""
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR IGNORE INTO assertion_method (
                method_key, name, category, description, example_code, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ASSERTION_METHOD_SEEDS,
        )
        conn.commit()
    except Exception:
        # 启动阶段不因目录种子失败阻断
        pass


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """初始化 SQLite 数据库（若表不存在则创建）"""
    conn = _get_conn()
    try:
        cur = conn.cursor()

        # 用例表（不再保存文件名/相对路径，仅保存名称与内容）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS test_case (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # 执行集表
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exec_set (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # 执行集-用例关联表
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exec_set_case (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exec_set_id TEXT NOT NULL,
                case_id INTEGER NOT NULL,
                order_no INTEGER,
                UNIQUE(exec_set_id, case_id)
            )
            """
        )

        # 公共方法（Python 源码片段，供用例复用）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public_method (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # 断言方法目录（uiautomator2 常用写法说明，系统预置、只读展示）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS assertion_method (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                example_code TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # 执行历史表（测试结果表）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exec_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                main_task_id TEXT,
                type TEXT,
                device_id TEXT,
                case_id INTEGER,
                exec_set_id TEXT,
                record_video INTEGER,
                video_path TEXT,
                status TEXT,
                create_time TEXT,
                start_time TEXT,
                end_time TEXT,
                exec_duration REAL,
                report_index_path TEXT,
                report_meta_path TEXT,
                pytest_returncode INTEGER,
                report_generate_duration REAL,
                error_msg TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        # 运行时任务表（记录当前/最近一次运行时状态，便于运行中任务管理）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                main_task_id TEXT,
                type TEXT,
                device_id TEXT,
                status TEXT,
                create_time TEXT,
                start_time TEXT,
                end_time TEXT,
                stop_reason TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        # 兼容旧库：若 test_case 仍存在 file_name/rel_path 字段，则迁移为仅 name+content 结构
        try:
            cur.execute("PRAGMA table_info(test_case)")
            cols = cur.fetchall()
            col_names = {c["name"] for c in cols}
            if "file_name" in col_names or "rel_path" in col_names:
                now_str_mig = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS test_case_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO test_case_new (id, name, content, created_at, updated_at)
                    SELECT
                        id,
                        name,
                        content,
                        COALESCE(created_at, ?),
                        COALESCE(updated_at, created_at, ?)
                    FROM test_case
                    """,
                    (now_str_mig, now_str_mig),
                )
                cur.execute("DROP TABLE test_case")
                cur.execute("ALTER TABLE test_case_new RENAME TO test_case")
        except Exception:
            # 若表不存在或迁移失败，则保持现状，避免影响启动
            pass

        # 为已有表补充缺失字段（兼容旧库）
        for sql in [
            # exec_set 时间字段（老库可能没有）
            "ALTER TABLE exec_set ADD COLUMN created_at TEXT",
            "ALTER TABLE exec_set ADD COLUMN updated_at TEXT",
            # exec_history 关联字段（用例ID、执行集ID）
            "ALTER TABLE exec_history ADD COLUMN case_id INTEGER",
            "ALTER TABLE exec_history ADD COLUMN exec_set_id TEXT",
            "ALTER TABLE exec_history ADD COLUMN record_video INTEGER",
            "ALTER TABLE exec_history ADD COLUMN video_path TEXT",
            # exec_history 时间/耗时字段
            "ALTER TABLE exec_history ADD COLUMN created_at TEXT",
            "ALTER TABLE exec_history ADD COLUMN updated_at TEXT",
            "ALTER TABLE exec_history ADD COLUMN exec_duration REAL",
            # exec_set_case 时间字段
            "ALTER TABLE exec_set_case ADD COLUMN created_at TEXT",
            "ALTER TABLE exec_set_case ADD COLUMN updated_at TEXT",
            # task_runtime 时间字段
            "ALTER TABLE task_runtime ADD COLUMN created_at TEXT",
            "ALTER TABLE task_runtime ADD COLUMN updated_at TEXT",
        ]:
            try:
                cur.execute(sql)
            except Exception:
                # 字段已存在时忽略错误
                pass

        # 为历史数据补充缺失的 created_at / updated_at 字段（统一写入当前时间）
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tbl in [
            "test_case",
            "exec_set",
            "exec_set_case",
            "public_method",
            "exec_history",
            "task_runtime",
        ]:
            # created_at 兜底
            try:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET created_at = ?
                    WHERE (created_at IS NULL OR created_at = '')
                    """,
                    (now_str,),
                )
            except Exception:
                # 兼容旧库：若表中不存在 created_at 字段或其他异常，忽略
                pass

            # updated_at 兜底
            try:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET updated_at = COALESCE(updated_at, created_at, ?)
                    WHERE (updated_at IS NULL OR updated_at = '')
                    """,
                    (now_str,),
                )
            except Exception:
                # 兼容旧库：若表中不存在 updated_at 字段或其他异常，忽略
                pass

        conn.commit()

        _seed_assertion_methods(conn)

        # 归一化历史状态（兼容旧值）：仅保留 success/failure/stop
        try:
            cur.execute(
                """
                UPDATE exec_history
                SET status = 'failure'
                WHERE LOWER(COALESCE(status, '')) = 'success_with_failure'
                """
            )
            cur.execute(
                """
                UPDATE exec_history
                SET status = 'failure'
                WHERE LOWER(COALESCE(status, '')) IN ('failed', 'error', 'exception')
                """
            )
            cur.execute(
                """
                UPDATE exec_history
                SET status = 'stop'
                WHERE LOWER(COALESCE(status, '')) IN ('stopped', 'cancelled', 'canceled')
                """
            )
            cur.execute(
                """
                UPDATE exec_history
                SET status = NULL
                WHERE LOWER(COALESCE(status, '')) IN ('pending', 'running', 'unknown')
                """
            )
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


_init_db()


# ------------- 用例相关操作 -------------


def list_cases() -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id,
                   name,
                   created_at,
                   updated_at
            FROM test_case
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_case(case_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, content
            FROM test_case
            WHERE id = ?
            """,
            (case_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_case(name: str, content: str) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO test_case (name, content, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, content, now, now),
        )
        conn.commit()
        case_id = cur.lastrowid
        log.info(f"创建用例成功：id={case_id}, name={name}")
        return {
            "id": case_id,
            "name": name,
        }
    finally:
        conn.close()


def update_case(case_id: int, name: Optional[str], content: Optional[str]) -> bool:
    if name is None and content is None:
        return True
    conn = _get_conn()
    try:
        cur = conn.cursor()
        fields: List[str] = []
        params: List[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        fields.append("updated_at = ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(case_id)
        sql = f"UPDATE test_case SET {', '.join(fields)} WHERE id = ?"
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_case(case_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM test_case WHERE id = ?", (case_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ------------- 公共方法相关操作 -------------


def list_public_methods_meta() -> List[Dict[str, Any]]:
    """列出公共方法（不含 content，便于列表展示）"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM public_method
            ORDER BY name COLLATE NOCASE ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_public_method(method_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description, content, created_at, updated_at
            FROM public_method
            WHERE id = ?
            """,
            (method_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_public_method(name: str, description: Optional[str], content: str) -> Optional[Dict[str, Any]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO public_method (name, description, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip(), (description or "").strip() or None, content, now, now),
            )
        except sqlite3.IntegrityError:
            return None
        conn.commit()
        mid = cur.lastrowid
        log.info(f"创建公共方法成功：id={mid}, name={name}")
        return {"id": mid, "name": name.strip()}
    finally:
        conn.close()


def update_public_method(
    method_id: int,
    name: Optional[str],
    description: Optional[str],
    content: Optional[str],
) -> bool:
    if name is None and description is None and content is None:
        return True
    conn = _get_conn()
    try:
        cur = conn.cursor()
        fields: List[str] = []
        params: List[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if description is not None:
            fields.append("description = ?")
            params.append((description or "").strip() or None)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        fields.append("updated_at = ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(method_id)
        sql = f"UPDATE public_method SET {', '.join(fields)} WHERE id = ?"
        try:
            cur.execute(sql, params)
        except sqlite3.IntegrityError:
            return False
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_public_method(method_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM public_method WHERE id = ?", (method_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ------------- 断言方法目录（只读展示） -------------


def list_assertion_methods() -> List[Dict[str, Any]]:
    """列出系统预置的 uiautomator2 断言说明（按分类与排序）。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, method_key, name, category, description, example_code, sort_order
            FROM assertion_method
            ORDER BY sort_order ASC, id ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ------------- 执行集相关操作 -------------


def list_exec_sets_with_case_count() -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT es.id,
                   es.name,
                   es.description,
                   es.created_at,
                   es.updated_at,
                   COUNT(esc.case_id) AS case_count
            FROM exec_set es
            LEFT JOIN exec_set_case esc ON es.id = esc.exec_set_id
            GROUP BY es.id, es.name, es.description, es.created_at, es.updated_at
            ORDER BY es.created_at DESC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_exec_sets() -> int:
    """统计执行集总数"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) AS cnt FROM exec_set")
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def get_exec_set_with_cases(exec_set_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM exec_set
            WHERE id = ?
            """,
            (exec_set_id,),
        )
        base = cur.fetchone()
        if not base:
            return None

        cur.execute(
            """
            SELECT esc.case_id,
                   tc.name
            FROM exec_set_case esc
            JOIN test_case tc ON esc.case_id = tc.id
            WHERE esc.exec_set_id = ?
            ORDER BY COALESCE(esc.order_no, esc.id) ASC
            """,
            (exec_set_id,),
        )
        cases = [dict(r) for r in cur.fetchall()]
        result = dict(base)
        result["cases"] = cases
        result["case_count"] = len(cases)
        return result
    finally:
        conn.close()


def create_exec_set_record(exec_set_id: str, name: str, description: str) -> Optional[Dict[str, Any]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO exec_set (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (exec_set_id, name, description, now, now),
            )
        except sqlite3.IntegrityError:
            # 名称唯一约束冲突
            return None
        conn.commit()
        return {
            "id": exec_set_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "cases": [],
            "case_count": 0,
        }
    finally:
        conn.close()


def update_exec_set_record(exec_set_id: str, name: Optional[str], description: Optional[str]) -> bool:
    if name is None and description is None:
        return True
    conn = _get_conn()
    try:
        cur = conn.cursor()
        fields: List[str] = []
        params: List[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        fields.append("updated_at = ?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(exec_set_id)
        sql = f"UPDATE exec_set SET {', '.join(fields)} WHERE id = ?"
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def overwrite_exec_set_cases(exec_set_id: str, case_ids: List[int]) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM exec_set_case WHERE exec_set_id = ?", (exec_set_id,))
        if case_ids:
            rows: List[Tuple[Any, ...]] = []
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for idx, cid in enumerate(case_ids):
                rows.append((exec_set_id, cid, idx, now, now))
            cur.executemany(
                """
                INSERT INTO exec_set_case (
                    exec_set_id, case_id, order_no, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_exec_set_case(exec_set_id: str, case_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM exec_set_case WHERE exec_set_id = ? AND case_id = ?",
            (exec_set_id, case_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_exec_set_record(exec_set_id: str) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM exec_set_case WHERE exec_set_id = ?", (exec_set_id,))
        cur.execute("DELETE FROM exec_set WHERE id = ?", (exec_set_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ------------- 执行历史相关操作 -------------


def upsert_history(
    task_id: str,
    main_task_id: Optional[str] = None,
    type_: Optional[str] = None,
    device_id: Optional[str] = None,
    case_id: Optional[int] = None,
    exec_set_id: Optional[str] = None,
    record_video: Optional[bool] = None,
    video_path: Optional[str] = None,
    status: Optional[str] = None,
    create_time: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    report_index_path: Optional[str] = None,
    report_meta_path: Optional[str] = None,
    pytest_returncode: Optional[int] = None,
    report_generate_duration: Optional[float] = None,
    error_msg: Optional[str] = None,
    exec_duration: Optional[float] = None,
) -> None:
    """
    以 task_id 为唯一键做“插入或更新”，只覆盖传入非 None 的字段。
    """
    status = normalize_history_status(status)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM exec_history WHERE task_id = ?",
            (task_id,),
        )
        exists = cur.fetchone() is not None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not exists:
            # 插入时需要补充 create_time / created_at / updated_at
            if create_time is None:
                create_time = now_str
            cur.execute(
                """
                INSERT INTO exec_history (
                    task_id, main_task_id, type, device_id,
                    case_id, exec_set_id, record_video, video_path, status,
                    create_time, start_time, end_time,
                    exec_duration,
                    report_index_path, report_meta_path,
                    pytest_returncode, report_generate_duration, error_msg,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    main_task_id,
                    type_,
                    device_id,
                    case_id,
                    exec_set_id,
                    (1 if record_video else 0) if record_video is not None else None,
                    video_path,
                    status,
                    create_time,
                    start_time,
                    end_time,
                    exec_duration,
                    report_index_path,
                    report_meta_path,
                    pytest_returncode,
                    report_generate_duration,
                    error_msg,
                    now_str,
                    now_str,
                ),
            )
        else:
            fields: List[str] = []
            params: List[Any] = []
            mapping = {
                "main_task_id": main_task_id,
                "type": type_,
                "device_id": device_id,
                "case_id": case_id,
                "exec_set_id": exec_set_id,
                "record_video": (1 if record_video else 0) if record_video is not None else None,
                "video_path": video_path,
                "status": status,
                "start_time": start_time,
                "end_time": end_time,
                 "exec_duration": exec_duration,
                "report_index_path": report_index_path,
                "report_meta_path": report_meta_path,
                "pytest_returncode": pytest_returncode,
                "report_generate_duration": report_generate_duration,
                "error_msg": error_msg,
            }
            for col, value in mapping.items():
                if value is not None:
                    fields.append(f"{col} = ?")
                    params.append(value)
            # 总是更新 updated_at
            fields.append("updated_at = ?")
            params.append(now_str)
            if fields:
                params.append(task_id)
                sql = f"UPDATE exec_history SET {', '.join(fields)} WHERE task_id = ?"
                cur.execute(sql, params)

        conn.commit()
    finally:
        conn.close()


def get_history_by_task_id(task_id: str) -> Optional[Dict[str, Any]]:
    """根据task_id查询一条执行历史"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM exec_history
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_histories(limit: int = 100) -> List[Dict[str, Any]]:
    """按创建时间倒序查询最近的执行历史（兼容旧接口：仅limit）"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT eh.*,
                   tc.name AS case_name,
                   es.name AS exec_set_name
            FROM exec_history eh
            LEFT JOIN test_case tc ON eh.case_id = tc.id
            LEFT JOIN exec_set es ON eh.exec_set_id = es.id
            ORDER BY eh.create_time DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_single_histories() -> int:
    """统计单用例（含子任务）执行历史数量（仅最终态）"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(1) AS cnt
            FROM exec_history
            WHERE (type IS NULL OR type = 'single')
              AND status IN ('success', 'failure', 'stop')
            """
        )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def list_single_histories_paginated(
    offset: int, limit: int
) -> List[Dict[str, Any]]:
    """分页查询单用例（含子任务）执行历史（仅最终态）"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT eh.*,
                   tc.name AS case_name
            FROM exec_history eh
            LEFT JOIN test_case tc ON eh.case_id = tc.id
            WHERE (eh.type IS NULL OR eh.type = 'single')
              AND eh.status IN ('success', 'failure', 'stop')
            ORDER BY eh.create_time DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_exec_set_histories(exec_set_id: Optional[str] = None) -> int:
    """统计执行集主任务历史数量（仅最终态），可按exec_set_id过滤。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if exec_set_id:
            cur.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM exec_history
                WHERE type = 'exec_set' AND exec_set_id = ?
                  AND status IN ('success', 'failure', 'stop')
                """,
                (exec_set_id,),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM exec_history
                WHERE type = 'exec_set'
                  AND status IN ('success', 'failure', 'stop')
                """
            )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def list_exec_set_histories_paginated(
    offset: int, limit: int, exec_set_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    分页查询执行集主任务历史（type='exec_set'），可按exec_set_id过滤。
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if exec_set_id:
            cur.execute(
                """
                SELECT eh.*,
                       es.name AS exec_set_name
                FROM exec_history eh
                LEFT JOIN exec_set es ON eh.exec_set_id = es.id
                WHERE eh.type = 'exec_set' AND eh.exec_set_id = ?
                  AND eh.status IN ('success', 'failure', 'stop')
                ORDER BY eh.create_time DESC
                LIMIT ? OFFSET ?
                """,
                (exec_set_id, limit, offset),
            )
        else:
            cur.execute(
                """
                SELECT eh.*,
                       es.name AS exec_set_name
                FROM exec_history eh
                LEFT JOIN exec_set es ON eh.exec_set_id = es.id
                WHERE eh.type = 'exec_set'
                  AND eh.status IN ('success', 'failure', 'stop')
                ORDER BY eh.create_time DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_histories_by_type(type_: Optional[str]) -> int:
    """
    统计执行历史数量。
    - type_ 为 None 时，统计单用例任务（type IS NULL 或 type='single'）
    - type_ 为 'exec_set' 时，仅统计执行集主任务
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if type_ is None:
            cur.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM exec_history
                WHERE type IS NULL OR type = 'single'
                """
            )
        else:
            cur.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM exec_history
                WHERE type = ?
                """,
                (type_,),
            )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def list_exec_set_histories(exec_set_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    查询执行集主任务的历史记录（type='exec_set'），可按exec_set_id过滤。
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if exec_set_id:
            cur.execute(
                """
                SELECT *
                FROM exec_history
                WHERE type = 'exec_set' AND exec_set_id = ?
                ORDER BY create_time DESC
                LIMIT ?
                """,
                (exec_set_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM exec_history
                WHERE type = 'exec_set'
                ORDER BY create_time DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_exec_set_history_detail(main_task_id: str) -> Optional[Dict[str, Any]]:
    """
    获取执行集主任务及其所有子任务的历史信息。

    返回结构：
    {
      "main": {...},          # 主任务history
      "sub_tasks": [...],     # 子任务history列表
    }
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 主任务
        cur.execute(
            """
            SELECT *
            FROM exec_history
            WHERE task_id = ? AND type = 'exec_set'
            """,
            (main_task_id,),
        )
        main_row = cur.fetchone()
        if not main_row:
            return None

        # 子任务：main_task_id = main_task_id
        cur.execute(
            """
            SELECT *
            FROM exec_history
            WHERE main_task_id = ?
            ORDER BY create_time ASC
            """,
            (main_task_id,),
        )
        sub_rows = cur.fetchall()

        return {
            "main": dict(main_row),
            "sub_tasks": [dict(r) for r in sub_rows],
        }
    finally:
        conn.close()


def upsert_task_runtime(
    task_id: str,
    main_task_id: Optional[str] = None,
    type_: Optional[str] = None,
    device_id: Optional[str] = None,
    status: Optional[str] = None,
    create_time: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    stop_reason: Optional[str] = None,
) -> None:
    """
    以 task_id 为唯一键做“插入或更新”，只覆盖传入非 None 的字段。
    用于运行中任务管理，与 exec_history 解耦。
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM task_runtime WHERE task_id = ?",
            (task_id,),
        )
        exists = cur.fetchone() is not None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not exists:
            if create_time is None:
                create_time = now_str
            cur.execute(
                """
                INSERT INTO task_runtime (
                    task_id, main_task_id, type, device_id,
                    status, create_time, start_time, end_time, stop_reason,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    main_task_id,
                    type_,
                    device_id,
                    status,
                    create_time,
                    start_time,
                    end_time,
                    stop_reason,
                    now_str,
                    now_str,
                ),
            )
        else:
            fields: List[str] = []
            params: List[Any] = []
            mapping = {
                "main_task_id": main_task_id,
                "type": type_,
                "device_id": device_id,
                "status": status,
                "start_time": start_time,
                "end_time": end_time,
                "stop_reason": stop_reason,
            }
            for col, value in mapping.items():
                if value is not None:
                    fields.append(f"{col} = ?")
                    params.append(value)
            # 总是更新 updated_at
            fields.append("updated_at = ?")
            params.append(now_str)
            if fields:
                params.append(task_id)
                sql = f"UPDATE task_runtime SET {', '.join(fields)} WHERE task_id = ?"
                cur.execute(sql, params)

        conn.commit()
    finally:
        conn.close()


def get_task_runtime(task_id: str) -> Optional[Dict[str, Any]]:
    """根据task_id查询一条运行时任务记录"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM task_runtime
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_running_tasks() -> List[Dict[str, Any]]:
    """
    查询运行中任务列表。
    这里的“运行中”包含 pending / running 两种状态，便于前端统一展示。
    仅返回 type != 'exec_set' 的任务（即单用例/子任务），避免执行集主任务重复计数。
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM task_runtime
            WHERE status IN ('pending', 'running')
              AND (type IS NULL OR type != 'exec_set')
            ORDER BY create_time DESC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

