#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础 YAML 读写工具（确保 conf 模块能正常加载配置）"""
import yaml
import os


def load_yaml(file_path: str) -> dict:
    """
    读取 YAML 文件并返回字典
    :param file_path: YAML 文件路径
    :return: 解析后的字典
    :raises FileNotFoundError: 文件不存在
    :raises yaml.YAMLError: YAML 格式错误
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"YAML 文件不存在：{file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # 允许 YAML 中包含注释，使用 safe_load 避免安全风险
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        # 捕获 YAML 格式错误，明确报错位置
        error_msg = f"解析 YAML 文件 {file_path} 失败："
        if hasattr(e, "problem_mark"):
            mark = e.problem_mark
            error_msg += f"行 {mark.line + 1}，列 {mark.column + 1}：{str(e)}"
        else:
            error_msg += str(e)
        raise yaml.YAMLError(error_msg) from e


def save_yaml(data: dict, file_path: str) -> None:
    """
    将字典写入 YAML 文件（备用功能）
    :param data: 要写入的字典
    :param file_path: 目标文件路径
    """
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
