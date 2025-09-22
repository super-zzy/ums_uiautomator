import pytest
import allure
import time


@allure.severity("normal")
@allure.feature("应用测试")
@allure.story("打开摄像头")
def test_case01(d):
    """测试打开设备摄像头"""
    with allure.step("解锁屏幕"):
        d.unlock()  # 执行解锁操作

    with allure.step("找到并点击相机图标"):
        assert d.check_text_exists("相机"), "未找到相机应用"
        d.click_text("相机")  # 点击文本为"相机"的控件

    with allure.step("验证相机已打开"):
        # 等待相机启动
        time.sleep(3)
        # 验证相机预览界面存在（根据实际UI调整验证条件）
        assert d.check_resource_exists("com.android.camera:id/shutter_button"), "相机未正常启动"

    with allure.step("退出相机"):
        d.press("back")  # 按返回键退出
        time.sleep(1)
        d.press("home")  # 返回主页


@allure.severity("normal")
@allure.feature("应用测试")
@allure.story("打开微信")
def test_case02(d):
    """测试打开微信并进入指定聊天"""
    with allure.step("解锁屏幕并返回主页"):
        d.unlock()
        d.press("home")

    with allure.step("启动微信应用"):
        assert d.app_start("com.tencent.mm"), "微信启动失败"
        time.sleep(5)  # 等待微信启动完成

    with allure.step("验证微信主界面"):
        assert d.check_resource_exists("com.tencent.mm:id/tab_layout"), "微信主界面加载失败"

    with allure.step("进入第一个聊天"):
        # 点击第一个聊天条目（根据实际UI调整坐标）
        assert d.click(500, 300), "点击聊天条目失败"
        time.sleep(2)

    with allure.step("发送测试消息"):
        # 输入消息内容（根据实际UI调整输入框资源ID）
        d.send_keys("com.tencent.mm:id/al_", "自动化测试消息")
        # 点击发送按钮
        assert d.click(1000, 1800), "发送消息失败"
        time.sleep(1)

    with allure.step("退出微信"):
        d.app_stop("com.tencent.mm")


@allure.severity("normal")
@allure.feature("系统功能测试")
@allure.story("调节屏幕亮度")
def test_case03(d):
    """测试调节设备屏幕亮度"""
    with allure.step("记录当前亮度"):
        original_brightness = d.get_brightness()
        allure.attach(f"原始亮度: {original_brightness}", "系统信息")

    with allure.step("将亮度调节至50%"):
        assert d.set_brightness(50), "亮度调节失败"
        time.sleep(2)
        current_brightness = d.get_brightness()
        assert abs(current_brightness - 50) < 5, "亮度调节未生效"

    with allure.step("恢复原始亮度"):
        d.set_brightness(original_brightness)
        time.sleep(1)
        assert abs(d.get_brightness() - original_brightness) < 5, "亮度恢复失败"


@allure.severity("normal")
@allure.feature("系统功能测试")
@allure.story("调节媒体音量")
def test_case04(d):
    """测试调节设备媒体音量"""
    with allure.step("记录当前媒体音量"):
        original_volume = d.get_volume("media")
        allure.attach(f"原始音量: {original_volume}", "系统信息")

    with allure.step("增加媒体音量"):
        assert d.set_volume("media", original_volume + 2), "音量调节失败"
        time.sleep(1)
        assert d.get_volume("media") == original_volume + 2, "音量增加未生效"

    with allure.step("减少媒体音量"):
        assert d.set_volume("media", original_volume), "音量调节失败"
        time.sleep(1)
        assert d.get_volume("media") == original_volume, "音量恢复失败"

