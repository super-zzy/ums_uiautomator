# @Time     : 2025/9/15 18:00
# @Author   : zyli3
# -*- coding: utf-8 -*-
import pytest
import allure


@allure.severity("normal")
@allure.feature("功能测试")
@allure.story("检查页面相机文本控件")
def test_case01(d):
    """检查页面是否存在'相机'文本"""
    assert d.check_text_exists("相机"), "页面未找到'相机'文本"


@allure.severity("blocker")
@allure.feature("功能测试")
@allure.story("检查页面QQ文本控件")
@pytest.mark.skipif(True, reason="演示跳过用例")
def test_case02(d):
    """检查页面是否存在'QQ'文本（跳过）"""
    assert d.check_text_exists("QQ"), "页面未找到'QQ'文本"


@allure.severity("blocker")
@allure.feature("API测试")
@allure.story("click参数不正确")
@allure.step("执行错误的click调用")
@pytest.mark.skipif(False, reason="演示失败用例")
def test_case03(d):
    """调用click时传递单参数（预期失败）"""
    with pytest.raises(Exception):
        d.click(100)  # 故意传递单参数，触发错误


@allure.severity("normal")
@allure.title("Case 04 测试正确的click")
@allure.feature("API测试")
@allure.story("click参数正确")
def test_case04(d):
    """测试正确的坐标点击"""
    with allure.step("第一次点击（100,100）"):
        assert d.click(100, 100), "第一次点击失败"

    with allure.step("第二次点击（200,200）"):
        assert d.click(200, 200), "第二次点击失败"
        d.log.info("两次点击操作完成，测试通过")