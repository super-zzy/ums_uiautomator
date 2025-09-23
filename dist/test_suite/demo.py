import pytest
import allure
import time


@allure.severity("normal")
@allure.feature("系统功能测试")
@allure.story("屏幕滑动操作")
def test_case01(d):
    """测试屏幕向左、向右滑动操作"""
    with allure.step("解锁屏幕"):
        d.unlock()  # 执行解锁操作
        time.sleep(1)

    with allure.step("向右滑动屏幕"):
        # 滑动参数：start_x, start_y, end_x, end_y, 滑动时长(ms)
        assert d.swipe(800, 500, 200, 500), "向右滑动失败"
        time.sleep(2)

    with allure.step("向左滑动屏幕"):
        assert d.swipe(200, 500, 800, 500), "向左滑动失败"
        time.sleep(2)


@allure.severity("normal")
@allure.feature("应用测试")
@allure.story("打开微信应用")
def test_case02(d):
    """测试打开微信应用并验证主界面"""
    with allure.step("解锁屏幕并返回主页"):
        d.unlock()
        d.press("home")
        time.sleep(3)

    with allure.step("启动微信应用"):
        d.app_start("com.tencent.mm", stop=True)
        time.sleep(5)  # 等待微信启动完成

    with allure.step("关闭微信应用"):
        d.app_stop("com.tencent.mm")
        time.sleep(1)