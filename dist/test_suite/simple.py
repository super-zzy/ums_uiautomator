import uiautomator2 as u2
import allure
import time


@allure.severity("normal")
@allure.feature("收银机")
@allure.story("B2C")
def test_case01(d):
    d = u2.connect('246NCCH09861')
    d.app_start('com.chinaums.catering', stop=True) # Start catering

    # 打开微信付款码
    d2 = u2.connect('AF8YVB1805003480')
    d2.app_start('com.tencent.mm', stop=True) # Start weixin

    d2.sleep(5) # Wait for splash screen ad to disappear

    d2.click(1002, 140) # 微信右上角+按钮

    d2.sleep(2) # Wait for splash screen ad to disappear

    sfkButton = d2.xpath('(//*[@resource-id="com.tencent.mm:id/m7g"])[4]') # sl is an XPathSelector object
    sfkButton.click()

    # 登录天天富餐饮
    username = d.xpath("//android.widget.EditText")
    username.set_text("") # Clear input field
    username.set_text("woozp") # Input "xgf123" into input field

    password = d.xpath("(//android.widget.EditText)[2]")
    password.set_text("") # Clear input field
    password.set_text("Aa123456") # Input "Aa@123456" into input field

    login = d.xpath("(//android.widget.TextView)[11]") # sl is an XPathSelector object
    login.click()

    d.sleep(1) # Wait for splash screen ad to disappear

    tab = d.xpath('(//*[@text="小青菜11"])[2]') # sl is an XPathSelector object
    tab.click()

    d.sleep(1) # Wait for splash screen ad to disappear

    d.click(420, 320)

    confirmButton = d.xpath("(//android.widget.Button)[2]") # sl is an XPathSelector object
    confirmButton.click()

    d.sleep(1) # Wait for splash screen ad to disappear

    settleButton = d.xpath("(//android.widget.TextView)[27]") # sl is an XPathSelector object
    settleButton.click()

    d.sleep(3) # Wait for splash screen ad to disappear

    wxButton = d.xpath("(//android.widget.ImageView)[12]") # sl is an XPathSelector object
    wxButton.click()




