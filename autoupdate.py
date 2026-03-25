import time
import json
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

HTML_FILE = "https://github.com/06E-Felicia/06E-Felicia.github.io/blob/main/index.html"
URL = "https://smca.fun/#/"

def fetch_smca():
    # print("📡 正在获取 SMCA 白鸟区雨量实况...")
    opt = Options()
    opt.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
    
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stat-number")))
        
        targets = {"分钟气温": "t", "最高气温": "th", "最低气温": "tl", "日雨量": "r_day", "1h滑动雨量": "r_1h", "海平面气压": "p"}
        res = {}
        items = driver.find_elements(By.CLASS_NAME, "stat-item")
        for i in items:
            lbl = i.find_element(By.CLASS_NAME, "stat-label").text.strip()
            val = i.find_element(By.CLASS_NAME, "stat-number").text.strip()
            if lbl in targets:
                res[targets[lbl]] = val
            if "time" not in res:
                res["time"] = i.find_element(By.CLASS_NAME, "stat-description").text.replace("数据时间: ", "").strip()
        return res
    except Exception as e:
        # print(f"❌ 抓取错误: {e}")
        return None
    finally:
        driver.quit()

def update_html(data):
    if not data: return
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 精准替换 LIVE_DATA 行，保留其他部分
    new_json = json.dumps(data, ensure_ascii=False)
    content = re.sub(r'const LIVE_DATA = \{.*?\};', f'const LIVE_DATA = {new_json};', content)
    
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    # print("✅ 实况同步成功！你可以去手动修改预报部分了。")

while True:
    update_html(fetch_smca())
    # break
    time.sleep(6000)