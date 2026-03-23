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

