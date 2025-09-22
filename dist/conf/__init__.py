# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import os
import sys  # 新增：确保能获取项目根目录
from util.yaml_util import load_yaml

# 修复：基于conf文件夹自身的路径，计算config.yaml的绝对路径
# 避免因执行脚本的目录不同导致路径错误（如在子目录执行python ../run.py）
CONF_DIR = os.path.dirname(os.path.abspath(__file__))  # 获取conf文件夹的绝对路径
CONFIG_PATH = os.path.join(CONF_DIR, "config.yaml")  # 拼接config.yaml的路径（确保一定存在）


# 加载配置（支持环境变量覆盖）
def load_config() -> dict:
    # 打包后优先读取当前目录下的conf/config.yaml
    if getattr(sys, 'frozen', False):
        # 可执行文件所在目录
        base_dir = os.path.dirname(sys.executable)
        CONFIG_PATH = os.path.join(base_dir, 'conf', 'config.yaml')
    else:
        # 开发环境路径
        CONFIG_PATH = os.path.join(CONF_DIR, 'config.yaml')

    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"配置文件不存在！路径：{CONFIG_PATH}")

    # 先检查config.yaml是否存在（不存在直接抛错，避免后续导入时隐藏问题）
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"配置文件不存在！路径：{CONFIG_PATH}\n请检查conf目录下是否有config.yaml")

    try:
        config = load_yaml(CONFIG_PATH)
    except Exception as e:
        raise RuntimeError(f"解析config.yaml失败！错误：{str(e)}") from e

    # 环境变量覆盖（优先级：环境变量 > YAML配置）
    config["path"]["test_suite_dir"] = os.getenv(
        "TEST_SUITE_DIR", config["path"]["test_suite_dir"]
    )
    config["path"]["report_root_dir"] = os.getenv(
        "REPORT_ROOT_DIR", config["path"]["report_root_dir"]
    )
    config["web"]["port"] = int(os.getenv("WEB_PORT", config["web"]["port"]))

    # 标准化路径（处理相对路径为绝对路径，基于项目根目录）
    PROJECT_ROOT = os.path.dirname(CONF_DIR)  # 项目根目录 = conf的父目录
    for path_key in config["path"]:
        # 若配置的是相对路径，基于项目根目录拼接；若是绝对路径，直接使用
        if not os.path.isabs(config["path"][path_key]):
            config["path"][path_key] = os.path.abspath(
                os.path.join(PROJECT_ROOT, config["path"][path_key])
            )

    return config


# 全局配置实例（程序启动时加载，确保初始化成功）
try:
    GlobalConfig = load_config()
except Exception as e:
    # 打印详细错误，帮助定位问题（如config.yaml缺失、格式错误）
    print(f"[FATAL] conf模块初始化失败！无法创建GlobalConfig：{str(e)}", file=sys.stderr)
    raise  # 主动抛错，避免后续模块导入时静默失败
