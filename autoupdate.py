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

# 修改为仓库内的相对路径
HTML_FILE = "index.html" 
URL = "https://smca.fun/#/"

def fetch_smca():
    print("📡 正在获取实况数据...")
    opt = Options()
    opt.add_argument("--headless")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    
    # GitHub Actions 环境建议写法
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
    
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 15) # 增加等待时间提高稳定性
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stat-number")))
        
        targets = {"分钟气温": "t", "最高气温": "th", "最低气温": "tl", "日雨量": "r_day", "1h滑动雨量": "r_1h", "海平面气压": "p"}
        res = {}
        
        # 获取所有数据项
        items = driver.find_elements(By.CLASS_NAME, "stat-item")
        for i in items:
            try:
                lbl = i.find_element(By.CLASS_NAME, "stat-label").text.strip()
                val = i.find_element(By.CLASS_NAME, "stat-number").text.strip()
                if lbl in targets:
                    res[targets[lbl]] = val
                if "time" not in res:
                    desc = i.find_element(By.CLASS_NAME, "stat-description").text
                    res["time"] = desc.replace("数据时间: ", "").strip()
            except:
                continue
        return res
    except Exception as e:
        print(f"❌ 抓取错误: {e}")
        return None
    finally:
        driver.quit()

def update_html(data):
    if not data: 
        print("⚠️ 未获取到有效数据，停止更新。")
        return
    
    if not os.path.exists(HTML_FILE):
        print(f"❌ 未找到文件: {HTML_FILE}")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 替换 JS 中的 LIVE_DATA 变量
    new_json = json.dumps(data, ensure_ascii=False)
    content = re.sub(r'const LIVE_DATA = \{.*?\};', f'const LIVE_DATA = {new_json};', content)
    
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 数据同步成功: {new_json}")

if __name__ == "__main__":
    data = fetch_smca()
    update_html(data)
