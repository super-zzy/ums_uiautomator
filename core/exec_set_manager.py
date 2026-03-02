# core/exec_set_manager.py
import os
from datetime import datetime
from typing import List, Dict, Optional
from util.log_util import LogUtil
from util.path_util import safe_join, read_json_file, write_json_file

# 初始化日志
logger = LogUtil("exec_set_manager").get_logger()

# 执行集JSON文件路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEC_SETS_JSON_PATH = safe_join(PROJECT_ROOT, "data", "exec_sets.json")


class ExecSetManager:
    """执行集管理核心类（增删改查）"""

    def __init__(self):
        """初始化：确保JSON文件存在"""
        if not os.path.exists(EXEC_SETS_JSON_PATH):
            write_json_file(EXEC_SETS_JSON_PATH, [])
            logger.info(f"初始化执行集JSON文件：{EXEC_SETS_JSON_PATH}")

    def _generate_auto_id(self, exec_sets: List[Dict]) -> int:
        """生成自增ID"""
        if not exec_sets:
            return 1
        max_id = max([item["id"] for item in exec_sets])
        return max_id + 1

    def _get_current_time(self) -> str:
        """获取当前时间字符串（格式：YYYY-MM-DD HH:MM:SS）"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ========== 新增执行集 ==========
    def add_exec_set(self, exec_set_info: Dict) -> Dict:
        """
        新增执行集
        :param exec_set_info: 执行集信息，示例：
               {"name": "登录测试集", "case_ids": [101,102], "desc": "描述", "creator": "admin"}
        :return: 新增后的执行集完整数据
        """
        # 参数校验
        if not exec_set_info.get("name"):
            logger.error("新增执行集失败：名称不能为空")
            raise ValueError("执行集名称不能为空")

        # 读取现有数据
        exec_sets = read_json_file(EXEC_SETS_JSON_PATH)

        # 构造新执行集数据
        new_id = self._generate_auto_id(exec_sets)
        current_time = self._get_current_time()
        new_exec_set = {
            "id": new_id,
            "name": exec_set_info["name"],
            "case_ids": exec_set_info.get("case_ids", []),
            "desc": exec_set_info.get("desc", ""),
            "creator": exec_set_info.get("creator", ""),
            "create_time": current_time,
            "update_time": current_time,
            "is_enabled": exec_set_info.get("is_enabled", True)
        }

        # 写入JSON文件
        exec_sets.append(new_exec_set)
        write_json_file(EXEC_SETS_JSON_PATH, exec_sets)

        logger.info(f"新增执行集成功：ID={new_id}，名称={new_exec_set['name']}")
        return new_exec_set

    # ========== 删除执行集 ==========
    def delete_exec_set(self, exec_set_id: int) -> bool:
        """
        删除执行集
        :param exec_set_id: 执行集ID
        :return: 是否删除成功
        """
        exec_sets = read_json_file(EXEC_SETS_JSON_PATH)
        # 查找并删除指定ID的执行集
        original_len = len(exec_sets)
        exec_sets = [item for item in exec_sets if item["id"] != exec_set_id]

        if len(exec_sets) == original_len:
            logger.warning(f"删除执行集失败：ID={exec_set_id} 不存在")
            return False

        # 写入修改后的数据
        write_json_file(EXEC_SETS_JSON_PATH, exec_sets)
        logger.info(f"删除执行集成功：ID={exec_set_id}")
        return True

    # ========== 修改执行集 ==========
    def update_exec_set(self, exec_set_id: int, update_info: Dict) -> Optional[Dict]:
        """
        修改执行集（修复ID匹配和参数校验）
        :param exec_set_id: 执行集ID
        :param update_info: 要更新的字段
        :return: 更新后的执行集数据
        """
        # 第一步：先校验ID是否存在（复用查询方法，避免重复逻辑）
        target_exec_set = self.get_exec_set_by_id(exec_set_id)
        if not target_exec_set:
            logger.warning(f"修改执行集失败：ID={exec_set_id} 不存在")
            return None

        # 第二步：读取所有执行集并更新
        exec_sets = read_json_file(EXEC_SETS_JSON_PATH)
        updated_exec_set = None

        for idx, item in enumerate(exec_sets):
            # 强制类型统一匹配
            if int(item["id"]) == int(exec_set_id):
                # 仅更新允许的字段，防止恶意修改
                allowed_fields = ["name", "case_ids", "desc", "creator", "is_enabled"]
                for key, value in update_info.items():
                    if key in allowed_fields:
                        # 对case_ids做特殊校验（避免非列表值）
                        if key == "case_ids" and not isinstance(value, list):
                            logger.error(f"修改执行集失败：case_ids必须是列表，当前值={value}")
                            raise ValueError("case_ids必须是整数列表")
                        exec_sets[idx][key] = value

                # 自动更新修改时间
                exec_sets[idx]["update_time"] = self._get_current_time()
                updated_exec_set = exec_sets[idx]
                break

        # 第三步：写入修改后的数据
        write_json_file(EXEC_SETS_JSON_PATH, exec_sets)
        logger.info(f"修改执行集成功：ID={exec_set_id}，更新字段={list(update_info.keys())}")
        return updated_exec_set

    # ========== 查询执行集 ==========
    def get_exec_set_by_id(self, exec_set_id: int) -> Optional[Dict]:
        """根据ID查询单个执行集"""
        # 新增：打印传入的ID和类型，方便调试
        logger.debug(f"尝试查询执行集：ID={exec_set_id}，类型={type(exec_set_id)}")

        exec_sets = read_json_file(EXEC_SETS_JSON_PATH)
        # 新增：打印当前JSON文件中的所有ID，对比排查
        existing_ids = [item["id"] for item in exec_sets]
        logger.debug(f"当前JSON文件中的执行集ID列表：{existing_ids}")

        for item in exec_sets:
            # 新增：强制类型统一（避免字符串ID和整数ID不匹配）
            if int(item["id"]) == int(exec_set_id):
                logger.debug(f"查询执行集成功：ID={exec_set_id}")
                return item

        logger.error(f"查询执行集失败：ID={exec_set_id} 不存在（现有ID：{existing_ids}）")
        return None

    def get_all_exec_sets(self, filter_enabled: bool = None) -> List[Dict]:
        """
        查询所有执行集
        :param filter_enabled: 过滤是否启用（None：不过滤；True：仅启用；False：仅禁用）
        :return: 执行集列表
        """
        exec_sets = read_json_file(EXEC_SETS_JSON_PATH)
        # 可选过滤
        if filter_enabled is not None:
            exec_sets = [item for item in exec_sets if item["is_enabled"] == filter_enabled]

        logger.info(f"查询执行集列表成功：总数={len(exec_sets)}")
        return exec_sets

    # ========== 给执行集添加用例 ==========
    def add_cases_to_exec_set(self, exec_set_id: int, case_ids: List[int]) -> Optional[Dict]:
        """
        给执行集添加用例（追加，不去重）
        :param exec_set_id: 执行集ID
        :param case_ids: 要添加的用例ID列表
        :return: 更新后的执行集数据（None表示ID不存在）
        """
        # 校验用例ID格式
        if not isinstance(case_ids, list) or not all(isinstance(cid, int) for cid in case_ids):
            logger.error(f"添加用例失败：用例ID格式错误，case_ids={case_ids}")
            raise ValueError("用例ID必须是整数列表")

        # 获取当前执行集
        current_exec_set = self.get_exec_set_by_id(exec_set_id)
        if not current_exec_set:
            return None

        # 追加用例ID
        new_case_ids = current_exec_set["case_ids"] + case_ids
        # 去重（可选，根据业务需求）
        new_case_ids = list(set(new_case_ids))

        # 更新执行集
        updated_exec_set = self.update_exec_set(exec_set_id, {"case_ids": new_case_ids})
        logger.info(f"给执行集添加用例成功：ID={exec_set_id}，新增用例数={len(case_ids)}，总用例数={len(new_case_ids)}")
        return updated_exec_set


# ========== 测试代码 ==========
if __name__ == "__main__":
    # 初始化管理器
    manager = ExecSetManager()

    # 1. 新增执行集
    new_set = manager.add_exec_set({
        "name": "测试执行集1",
        "case_ids": [101, 102],
        "desc": "测试新增执行集",
        "creator": "test"
    })
    print("新增执行集：", new_set)

    # 2. 查询单个执行集
    exec_set = manager.get_exec_set_by_id(new_set["id"])
    print("查询单个执行集：", exec_set)

    # 3. 给执行集添加用例
    updated_set = manager.add_cases_to_exec_set(new_set["id"], [103, 104])
    print("添加用例后：", updated_set)

    # 4. 修改执行集
    modified_set = manager.update_exec_set(new_set["id"], {"name": "修改后的执行集名称", "is_enabled": False})
    print("修改后：", modified_set)

    # 5. 查询所有执行集
    all_sets = manager.get_all_exec_sets()
    print("所有执行集：", all_sets)

    # 6. 删除执行集
    delete_result = manager.delete_exec_set(new_set["id"])
    print("删除结果：", delete_result)