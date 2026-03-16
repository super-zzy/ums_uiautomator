# @Time     : 2025/9/16 10:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from util.log_util import TempLog
from core import db

log = TempLog()


class ExecSetManager:
    """执行集管理类（CRUD + 数据持久化）"""

    @classmethod
    def get_all_exec_sets(cls) -> List[Dict]:
        """获取所有执行集"""
        try:
            return db.list_exec_sets_with_case_count()
        except Exception as e:
            log.error(f"从SQLite加载执行集失败：{str(e)}", exc_info=True)
            return []

    @classmethod
    def get_exec_set_by_id(cls, exec_set_id: str) -> Optional[Dict]:
        """根据ID获取执行集"""
        try:
            return db.get_exec_set_with_cases(exec_set_id)
        except Exception as e:
            log.error(f"根据ID获取执行集失败：{str(e)}", exc_info=True)
            return None

    @classmethod
    def create_exec_set(cls, name: str, desc: str = "") -> Optional[Dict]:
        """创建新执行集"""
        exec_set_id = str(uuid.uuid4())[:8]  # 8位短ID
        exec_set = db.create_exec_set_record(exec_set_id, name, desc or "")
        if exec_set is None:
            log.warning(f"执行集名称已存在：{name}")
            return None
        log.info(f"创建执行集成功：{exec_set_id} - {name}")
        return exec_set

    @classmethod
    def update_exec_set(cls, exec_set_id: str, name: Optional[str] = None, desc: Optional[str] = None) -> bool:
        """更新执行集基本信息"""
        try:
            ok = db.update_exec_set_record(exec_set_id, name, desc)
            if not ok:
                log.warning(f"更新执行集失败或不存在：{exec_set_id}")
            return ok
        except Exception as e:
            log.error(f"更新执行集失败：{str(e)}", exc_info=True)
            return False

    @classmethod
    def add_cases_to_exec_set(cls, exec_set_id: str, cases: List[Dict]) -> bool:
        """添加用例到执行集（去重）"""
        # 兼容旧接口：从 DB 取出已有 case_id，再与传入的合并
        try:
            current = db.get_exec_set_with_cases(exec_set_id)
            if not current:
                return False
            existing_ids = {c["case_id"] for c in current.get("cases", [])}
            incoming_ids = {c.get("suite_id") for c in cases if c.get("suite_id") is not None}
            merged_ids = list(existing_ids | incoming_ids)
            db.overwrite_exec_set_cases(exec_set_id, merged_ids)
            log.info(f"执行集{exec_set_id}添加{len(incoming_ids - existing_ids)}个用例（累计{len(merged_ids)}个）")
            return True
        except Exception as e:
            log.error(f"执行集{exec_set_id}添加用例失败：{str(e)}", exc_info=True)
            return False

    @classmethod
    def set_cases_for_exec_set(cls, exec_set_id: str, cases: List[Dict]) -> bool:
        """
        覆盖设置执行集内的用例列表
        cases元素格式示例：
        {
            "suite_id": 0,
            "abs_path": "/xxx/test_demo.py",
            "name": "test_demo.py",
            "rel_path": "test_demo.py"
        }（这里的suite_id视为case_id）
        """
        try:
            uniq_ids = []
            seen = set()
            for c in cases:
                cid = c.get("suite_id")
                if cid is None or cid in seen:
                    continue
                seen.add(cid)
                uniq_ids.append(int(cid))
            ok = db.overwrite_exec_set_cases(exec_set_id, uniq_ids)
            if ok:
                log.info(f"执行集{exec_set_id}用例列表已更新，共{len(uniq_ids)}个用例")
            else:
                log.warning(f"尝试更新不存在的执行集：{exec_set_id}")
            return ok
        except Exception as e:
            log.error(f"设置执行集{exec_set_id}用例列表失败：{str(e)}", exc_info=True)
            return False

    @classmethod
    def remove_case_from_exec_set(cls, exec_set_id: str, suite_id: int) -> bool:
        """从执行集中移除单个用例"""
        try:
            ok = db.remove_exec_set_case(exec_set_id, int(suite_id))
            if ok:
                log.info(f"执行集{exec_set_id}移除用例case_id={suite_id}")
            return ok
        except Exception as e:
            log.error(f"执行集{exec_set_id}移除用例失败：{str(e)}", exc_info=True)
            return False

    @classmethod
    def delete_exec_set(cls, exec_set_id: str) -> bool:
        """删除执行集"""
        try:
            ok = db.delete_exec_set_record(exec_set_id)
            if ok:
                log.info(f"删除执行集：{exec_set_id}")
            return ok
        except Exception as e:
            log.error(f"删除执行集失败：{str(e)}", exc_info=True)
            return False
