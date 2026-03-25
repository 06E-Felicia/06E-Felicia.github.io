import requests
from bs4 import BeautifulSoup
import time
import json
import re

# 你的 HTML 文件路径
HTML_FILE_PATH = "index.html" 

def fetch_sz_warnings():
    url = "https://weather.sz.gov.cn/qixiangfuwu/yujingfuwu/tufashijianyujing/index.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 定位深圳预警区域
        warn_icons = []
        sz_div = soup.find('div', class_='tit fl tit_sz')
        if sz_div:
            imgs = sz_div.find_all('img')
            for img in imgs:
                src = img.get('src')
                if src:
                    warn_icons.append(src)
        
        return warn_icons
    except Exception as e:
        print(f"爬取失败: {e}")
        return []

def update_html():
    warnings = fetch_sz_warnings()
    
    with open(HTML_FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # 使用正则替换 HTML 中的 WARNINGS 变量内容
    # 匹配 const WARNINGS = [...];
    new_data = f"const WARNINGS = {json.dumps(warnings)};"
    content = re.sub(r'const WARNINGS = \[.*?\];', new_data, content)

    with open(HTML_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"[{time.strftime('%H:%M:%S')}] 更新成功，当前预警数: {len(warnings)}")

if __name__ == "__main__":
    while True:
        update_html()
        time.sleep(600)  # 600秒 = 10分钟
