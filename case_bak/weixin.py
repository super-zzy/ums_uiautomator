import pytest
import allure

# 一个自定义的前置和收尾，将会在 setup_and_teardown_demo 的前置后执行前置，收尾前执行收尾
@pytest.fixture(scope="function")
def d(setup_and_teardown_demo):
    """
    额外前置收尾，将实例化对象重命名
    @Author: zyli3
    @Create: 2025/9/15 18:00
    :return: Uiautomator
    """
    print("Setup")
    yield setup_and_teardown_demo
    print("Teardown")


@allure.severity("normal")
@allure.feature("功能测试")
@allure.story("打开微信收付款")
def test_case01(d):
    d.app_start('com.tencent.mm', stop=True) # Start catering

    d.click(1002, 140)

    sfkButton = d.xpath('(//*[@resource-id="com.tencent.mm:id/m7g"])[4]')  # sl is an XPathSelector object
    sfkButton.click()