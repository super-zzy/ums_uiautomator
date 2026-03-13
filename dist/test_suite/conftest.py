# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import pytest
from core.device_manager import DeviceManager
from core.uiautomator import Uiautomator


# 1. 注册命令行参数（供Web端传递设备ID和任务ID）
def pytest_addoption(parser):
    parser.addoption(
        "--device_id",
        action="store",
        required=True,
        help="Android设备ID（通过adb devices查看）"
    )
    parser.addoption(
        "--task_id",
        action="store",
        required=True,
        help="测试任务ID（用于日志和报告命名）"
    )


# 2. 设备实例夹具（session级别，全局共享）
@pytest.fixture(scope="session")
def device_id(request):
    return request.config.getoption("--device_id")


@pytest.fixture(scope="session")
def task_id(request):
    return request.config.getoption("--task_id")


@pytest.fixture(scope="session")
def uiautomator_instance(device_id, task_id) -> Uiautomator:
    """
    设备实例夹具（session级别，确保非None）
    :return: Uiautomator实例（已初始化完成）
    """
    # 从DeviceManager获取实例（确保初始化成功，失败则抛出异常）
    return DeviceManager.get_uiautomator_instance(device_id, task_id)


# 3. 测试用例前置/后置夹具（function级别）
@pytest.fixture(scope="function")
def setup_and_teardown_demo(uiautomator_instance):
    """
    通用前置：亮屏
    通用后置：回到主页面
    :param uiautomator_instance: Uiautomator实例（依赖注入）
    :return: Uiautomator实例
    """
    # 前置操作：亮屏
    uiautomator_instance.screen_on()
    yield uiautomator_instance

    # 后置操作：回到主页面
    uiautomator_instance.press("home")


# 4. 简化用例调用的夹具（可选）
@pytest.fixture(scope="function")
def d(setup_and_teardown_demo):
    """简化用例中设备实例的调用（d = setup_and_teardown_demo）"""
    return setup_and_teardown_demo