import sqlite3
from datetime import datetime

from core.db import DB_PATH


def migrate() -> None:
    """
    删除 test_case 表中的 file_name / rel_path 字段（如存在），并迁移数据到新表结构。
    该脚本是幂等的，多次执行不会报错。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # 查询现有列信息
        cur.execute("PRAGMA table_info(test_case)")
        cols = cur.fetchall()
        if not cols:
            print("表 test_case 不存在，跳过。")
            return

        col_names = {c["name"] for c in cols}
        if "file_name" not in col_names and "rel_path" not in col_names:
            print("test_case 表中已不存在 file_name / rel_path 字段，无需迁移。")
            return

        print("检测到旧结构 test_case（包含 file_name / rel_path），开始迁移...")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 创建新表，仅保留需要的字段
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

        # 将旧表数据迁移到新表，时间字段兜底
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
            (now_str, now_str),
        )

        # 删除旧表并重命名新表
        cur.execute("DROP TABLE test_case")
        cur.execute("ALTER TABLE test_case_new RENAME TO test_case")

        conn.commit()
        print("迁移完成：已删除 file_name / rel_path 字段。")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()

