import uiautomator2 as u2
import allure
import time


@allure.severity("normal")
@allure.feature("收银机")
@allure.story("B2C")
def test_case01(d):
    d = u2.connect('246NCCH09861')
    d.app_start('com.chinaums.catering', stop=True) # Start catering

    # 登录天天富餐饮
    username = d.xpath("//android.widget.EditText")
    username.set_text("") # Clear input field
    username.set_text("woozp") # Input "xgf123" into input field

    password = d.xpath("(//android.widget.EditText)[2]")
    password.set_text("") # Clear input field
    password.set_text("Aa123456") # Input "Aa@123456" into input field

    login = d.xpath("(//android.widget.TextView)[11]") # sl is an XPathSelector object
    login.click()




