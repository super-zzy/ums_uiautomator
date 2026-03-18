import uiautomator2 as u2
import time


def test_recorded_case(device_id="AF8YVB1805003480"):
    """
    通过 UI 自动化平台录制生成的示例用例。
    可根据需要自行补充断言等逻辑。
    """
    d = u2.connect(device_id)
    d.healthcheck()  # 确保会话可用

    # 录制动作回放开始
    d.swipe(893, 1034, 76, 1046, 0.2)
    d.click(76, 1046)
    time.sleep(4.0)
    # 点击元素（text='无障碍服务', resourceId='com.github.uiautomator:id/accessibility'）
    d(resourceId="com.github.uiautomator:id/accessibility", text="无障碍服务").click()
