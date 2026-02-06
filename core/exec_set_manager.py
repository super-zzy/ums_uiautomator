# @Time     : 2025/9/16 10:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from util.log_util import TempLog
from util.path_util import safe_join

log = TempLog()

# 执行集数据存储路径
EXEC_SET_STORAGE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "exec_sets.json")

# 确保存储目录存在
os.makedirs(os.path.dirname(EXEC_SET_STORAGE), exist_ok=True)


class ExecSetManager:
    """执行集管理类（CRUD + 数据持久化）"""

    @staticmethod
    def _load_exec_sets() -> List[Dict]:
        """加载所有执行集（从JSON文件）"""
        if not os.path.exists(EXEC_SET_STORAGE):
            return []
        try:
            with open(EXEC_SET_STORAGE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"加载执行集失败：{str(e)}", exc_info=True)
            return []

    @staticmethod
    def _save_exec_sets(exec_sets: List[Dict]) -> bool:
        """保存执行集到JSON文件"""
        try:
            with open(EXEC_SET_STORAGE, "w", encoding="utf-8") as f:
                json.dump(exec_sets, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            log.error(f"保存执行集失败：{str(e)}", exc_info=True)
            return False

    @classmethod
    def get_all_exec_sets(cls) -> List[Dict]:
        """获取所有执行集"""
        exec_sets = cls._load_exec_sets()
        # 补充用例数量等扩展字段
        for es in exec_sets:
            es["case_count"] = len(es.get("cases", []))
        return exec_sets

    @classmethod
    def get_exec_set_by_id(cls, exec_set_id: str) -> Optional[Dict]:
        """根据ID获取执行集"""
        exec_sets = cls._load_exec_sets()
        for es in exec_sets:
            if es["id"] == exec_set_id:
                return es
        return None

    @classmethod
    def create_exec_set(cls, name: str, desc: str = "") -> Optional[Dict]:
        """创建新执行集"""
        exec_sets = cls._load_exec_sets()
        # 校验名称唯一性
        if any(es["name"] == name for es in exec_sets):
            log.warning(f"执行集名称已存在：{name}")
            return None

        exec_set = {
            "id": str(uuid.uuid4())[:8],  # 8位短ID
            "name": name,
            "description": desc,
            "cases": [],  # 格式：[{"suite_id": 0, "abs_path": "/xxx/test.py"}, ...]
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        exec_sets.append(exec_set)
        if cls._save_exec_sets(exec_sets):
            log.info(f"创建执行集成功：{exec_set['id']} - {name}")
            return exec_set
        return None

    @classmethod
    def update_exec_set(cls, exec_set_id: str, name: Optional[str] = None, desc: Optional[str] = None) -> bool:
        """更新执行集基本信息"""
        exec_sets = cls._load_exec_sets()
        for es in exec_sets:
            if es["id"] == exec_set_id:
                if name:
                    # 校验名称唯一性（排除自身）
                    if any(e["name"] == name for e in exec_sets if e["id"] != exec_set_id):
                        log.warning(f"执行集名称已存在：{name}")
                        return False
                    es["name"] = name
                if desc is not None:
                    es["description"] = desc
                es["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return cls._save_exec_sets(exec_sets)
        return False

    @classmethod
    def add_cases_to_exec_set(cls, exec_set_id: str, cases: List[Dict]) -> bool:
        """添加用例到执行集（去重）"""
        exec_sets = cls._load_exec_sets()
        for es in exec_sets:
            if es["id"] == exec_set_id:
                existing_case_ids = {c["suite_id"] for c in es["cases"]}
                new_cases = [c for c in cases if c["suite_id"] not in existing_case_ids]
                es["cases"].extend(new_cases)
                es["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log.info(f"执行集{exec_set_id}添加{len(new_cases)}个用例（累计{len(es['cases'])}个）")
                return cls._save_exec_sets(exec_sets)
        return False

    @classmethod
    def remove_case_from_exec_set(cls, exec_set_id: str, suite_id: int) -> bool:
        """从执行集中移除单个用例"""
        exec_sets = cls._load_exec_sets()
        for es in exec_sets:
            if es["id"] == exec_set_id:
                original_count = len(es["cases"])
                es["cases"] = [c for c in es["cases"] if c["suite_id"] != suite_id]
                if len(es["cases"]) != original_count:
                    es["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log.info(f"执行集{exec_set_id}移除用例suite_id={suite_id}")
                    return cls._save_exec_sets(exec_sets)
                return True  # 用例不存在，视为成功
        return False

    @classmethod
    def delete_exec_set(cls, exec_set_id: str) -> bool:
        """删除执行集"""
        exec_sets = cls._load_exec_sets()
        new_exec_sets = [es for es in exec_sets if es["id"] != exec_set_id]
        if len(new_exec_sets) != len(exec_sets):
            log.info(f"删除执行集：{exec_set_id}")
            return cls._save_exec_sets(new_exec_sets)
        return False