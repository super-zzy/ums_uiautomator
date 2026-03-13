# -*- mode: python ; coding: utf-8 -*-
import os
import sys

import uiautomator2
import yaml
import pytest_timeout
from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.datastruct import Tree

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))

# 分析项目依赖
a = Analysis(
    ['run.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    # 重点：确保 conf 目录下的所有文件（包括 config.yaml）被打包
    datas=[
        # 方式1：打包整个 conf 目录（推荐，包含所有配置文件）
        (os.path.join(PROJECT_ROOT, 'conf'), 'conf'),
        # 其他必要目录...
        (os.path.join(PROJECT_ROOT, 'test_suite'), 'test_suite'),
        (os.path.join(PROJECT_ROOT, 'core'), 'core'),
        (os.path.join(PROJECT_ROOT, 'app', 'templates'), 'app/templates'),
        # 按当前运行环境动态获取第三方库路径，避免硬编码 Python 安装目录
        (os.path.dirname(uiautomator2.__file__), 'uiautomator2'),
        (os.path.dirname(yaml.__file__), 'yaml'),
        (os.path.dirname(pytest_timeout.__file__), 'pytest-timeout'),
    ],
    hiddenimports=[
        'yaml', 'flask', 'apscheduler', 'uiautomator2', 'yaml', 'pytest-timeout', 'pytest', 'allure_pytest', 'core', 'core.device_manager', 'core.uiautomator'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False
)

# 生成PYZ文件（打包字节码）
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 生成可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='UmsUiautomator',  # 可执行文件名称
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 启用压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台窗口（调试用，发布时可改为False）
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)