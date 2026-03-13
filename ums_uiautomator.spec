# -*- mode: python ; coding: utf-8 -*-
import os
import sys

import uiautomator2
import yaml
import pytest_timeout
from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))

# uiautomator2 的 u2.jar 位置（安装包里的 assets/u2.jar）
UIA2_JAR_PATH = os.path.join(
    os.path.dirname(uiautomator2.__file__),
    "assets",
    "u2.jar",
)

a = Analysis(
    ['run.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'conf'), 'conf'),
        (os.path.join(PROJECT_ROOT, 'test_suite'), 'test_suite'),
        (os.path.join(PROJECT_ROOT, 'core'), 'core'),
        (os.path.join(PROJECT_ROOT, 'app', 'templates'), 'app/templates'),
        # uiautomator2 运行时需要的 u2.jar，放到打包后的 uiautomator2/assets 目录下
        # 这样 uiautomator2.utils.with_package_resource 才能在包内正确找到 assets/u2.jar
        (UIA2_JAR_PATH, os.path.join('uiautomator2', 'assets')),
    ],
    hiddenimports=[
        'yaml', 'flask', 'apscheduler', 'uiautomator2', 'yaml',
        'pytest-timeout', 'pytest', 'allure_pytest', 'core',
        'core.device_manager', 'core.uiautomator'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
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