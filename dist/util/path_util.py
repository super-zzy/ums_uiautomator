# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os


def safe_join(base_dir: str, *paths: str) -> str:
    """
    安全拼接路径（防止路径穿越攻击）
    :param base_dir: 基础目录（限制所有路径在此目录下）
    :param paths: 待拼接的子路径
    :return: 安全的绝对路径
    :raises ValueError: 路径超出基础目录范围
    """
    base_abs = os.path.abspath(base_dir)
    target_path = os.path.abspath(os.path.join(base_abs, *paths))

    # 校验目标路径是否在基础目录内
    if not target_path.startswith(base_abs):
        raise ValueError(f"非法路径：{os.path.join(*paths)}（超出基础目录{base_dir}）")
    return target_path


def ensure_dir_exists(dir_path: str) -> None:
    """确保目录存在，不存在则创建"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

def get_file_size(path: str, unit: str = "KB") -> float:
    """
    计算文件或目录大小
    :param path: 文件/目录路径
    :param unit: 单位（B/KB/MB/GB）
    :return: 大小（保留2位小数）
    """
    if not os.path.exists(path):
        return 0.0

    total_size = 0
    if os.path.isfile(path):
        total_size = os.path.getsize(path)
    else:
        for root, _, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)

    # 单位转换
    unit_map = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    if unit not in unit_map:
        unit = "KB"
    return round(total_size / unit_map[unit], 2)
