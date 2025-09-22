# UMS UIAutomator 工具使用手册

## 简介
UMS UIAutomator 是一款基于UI自动化的测试工具，支持对Android设备进行自动化操作与验证。工具采用Python开发，集成Flask Web框架提供可视化操作界面，结合pytest测试框架和Allure报告系统，可打包为exe文件独立运行，适用于各类Android UI自动化测试场景。

## 环境要求
- 操作系统：Windows 10/11（64位）
- 目标设备：Android 7.0及以上系统的手机/模拟器
- 其他：
  - 需开启设备USB调试模式，并安装对应手机驱动
  - 无需预先安装Python环境（exe版本已打包运行时）

## 安装与启动
1. 从官方渠道获取工具安装包（`ums_uiautomator.exe`）
2. 双击运行exe文件，工具将自动初始化运行环境（首次启动可能需要几秒）
3. 启动成功后，会自动在当前目录创建以下文件夹：
   - `test_suite`：存放测试用例（.py文件）
   - `result`：存放测试日志、截图及Allure报告
   - `logs`：存放系统运行日志

## 界面说明
工具提供Web可视化操作界面，主要包含以下功能区域：
1. **状态概览区**：显示在线设备数、可用测试用例数和运行中任务数
2. **设备列表区**：展示当前已连接的Android设备，支持刷新设备列表
3. **测试配置区**：
   - 测试用例选择下拉框
   - 测试控制按钮（启动/停止测试、查看报告）
   - 用例管理按钮（新建/编辑/删除用例）
4. **任务日志区**：实时显示测试任务的执行状态和日志信息

## 基本操作流程
1. **设备连接**：
   - 通过USB连接Android设备到电脑
   - 确保设备已开启USB调试模式
   - 在工具界面点击"刷新"按钮，确认设备已显示在在线设备列表中

2. **测试用例管理**：
   - **新建用例**：点击"新建用例"按钮，输入文件名（.py后缀），编写测试脚本
   - **编辑用例**：从下拉框选择已有用例，点击"编辑用例"进行修改
   - **删除用例**：选择用例后点击"删除用例"（删除前请确认备份）

3. **执行测试**：
   - 从设备列表选择目标设备
   - 从下拉框选择要执行的测试用例
   - 点击"启动测试"按钮，任务日志区将显示实时执行状态
   - 如需终止测试，可点击"停止测试"按钮

4. **查看报告**：
   - 测试完成后，"查看报告"按钮将被激活
   - 点击按钮将自动打开Allure测试报告（HTML格式）
   - 报告中包含测试结果统计、详细步骤、截图及错误信息

## 测试报告说明
测试报告采用Allure格式生成，主要包含以下内容：
- **概览统计**：总用例数、通过数、失败数、跳过数等统计信息
- **测试详情**：每个测试用例的执行步骤、耗时、结果状态
- **截图对比**：支持测试过程中的截图对比（如UI差异分析）
- **多语言支持**：报告界面支持中文、英文、日文等多种语言切换

## 常见问题
1. **设备连接失败**：
   - 检查USB调试是否开启（设置->开发者选项）
   - 尝试重新安装设备驱动（可通过手机助手自动安装）
   - 更换USB线缆或接口，部分电脑前置USB接口供电不足

2. **测试用例执行失败**：
   - 检查设备是否处于解锁状态（锁屏会导致UI操作失败）
   - 确认测试用例中的应用包名、控件ID是否正确
   - 查看任务日志区或Allure报告中的详细错误信息

3. **报告无法生成**：
   - 检查磁盘空间是否充足
   - 确认测试是否正常执行（至少生成部分日志）
   - 查看`logs`目录下的系统日志定位问题

4. **工具启动失败**：
   - 确保当前用户有读写工具目录的权限
   - 关闭杀毒软件后重试（部分安全软件可能拦截exe运行）
   - 尝试以管理员身份运行

## 附录：测试用例示例

### 测试用例1：打开摄像头
```python
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
```

### 测试用例2：打开微信并发送消息
```python
import pytest
import allure
import time

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
```

### 测试用例3：调节设备亮度
```python
import pytest
import allure
import time

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
```

### 测试用例4：验证音量调节功能
```python
import pytest
import allure
import time

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
```