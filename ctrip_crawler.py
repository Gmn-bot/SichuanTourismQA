import requests
from bs4 import BeautifulSoup
import time
import csv
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
PAGE_URL_TEMPLATE = "https://you.ctrip.com/sightlist/chengdu104/s0-p{}.html"
START_PAGE = 1
END_PAGE = 200  # 爬取几页数据，可以根据需要调整
REQUEST_TIMEOUT = 30  # 增加超时时间以防止网络延迟
SELENIUM_WAIT_TIME = 30  # 增加等待时间，确保动态内容加载完成
SUBPAGE_NAV_DELAY = 5  # 增加子页面导航后等待时间，确保页面完全加载
PAGE_DELAY = 5  # 每页处理后的等待时间，避免请求过于频繁
SAVE_INTERVAL = 10  # 每爬取多少页保存一次数据，避免数据丢失
OUTPUT_CSV_FILE = "e:\\ZSTP\\qimo\\完整数据爬取.csv"  # 输出CSV文件路径
OUTPUT_TEMP_FILE = "e:\\ZSTP\\qimo\\temp_爬取数据.csv"  # 临时文件路径，用于定期保存

SUB_PAGE_HEADERS = { # Kept if you ever mix requests and selenium, but less critical for selenium driver.get()
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Connection": "keep-alive"
}

# --- Helper Functions for Data Extraction (Copied from previous response) ---
def get_text_or_na(element, strip=True, separator=' '):
    """Safely extracts text from a BeautifulSoup element."""
    if element:
        try:
            text = element.get_text(separator=separator)
            return text.strip() if strip else text
        except Exception:
            try:
                text = element.text
                return text.strip() if strip else text
            except Exception:
                return "N/A"
    return "N/A"

def extract_name(soup_subpage):
    """Extract attraction name"""
    name_element = soup_subpage.select_one('div.titleView div.title h1')
    if name_element: return name_element.text.strip()
    name_element = soup_subpage.select_one('div.title h1')
    if name_element: return name_element.text.strip()
    return "N/A"

def extract_score(soup_subpage):
    """Extract attraction score"""
    score_element = soup_subpage.select_one('p.commentScoreNum')
    if score_element: return score_element.text.strip()
    score_element = soup_subpage.select_one('div.commentScore p.commentScoreNum')
    if score_element: return score_element.text.strip()
    score_element = soup_subpage.select_one('div.title span.ef4gt2x5')
    if score_element: return score_element.text.strip()
    return "N/A"

def extract_popularity(soup_subpage):
    """Extract popularity/heat rating"""
    popularity_element = soup_subpage.select_one('div.heatScoreView div.heatScoreText')
    if popularity_element: return popularity_element.text.strip()
    popularity_element = soup_subpage.select_one('div.popularity span')
    if popularity_element: return popularity_element.text.strip()
    heat_sub_text = soup_subpage.select_one('div.heatSubView span.heatSubText')
    if heat_sub_text and heat_sub_text.previous_sibling:
        value_candidate = heat_sub_text.find_previous_sibling(string=True)
        if value_candidate and value_candidate.strip(): return value_candidate.strip()
        value_candidate_tag = heat_sub_text.find_previous_sibling()
        if value_candidate_tag : return value_candidate_tag.text.strip()
    return "N/A"

def extract_address(soup_subpage):
    """Extract attraction address"""
    items = soup_subpage.select('div.baseInfoModule div.baseInfoContent div.baseInfoItem')
    for item in items:
        title_element = item.select_one('p.baseInfoTitle')
        if title_element and '地址' in title_element.text:
            address_element = item.select_one('p.baseInfoText')
            if address_element: return address_element.text.strip()
    return "N/A"

def extract_opening_hours(soup_subpage):
    """Extract opening hours"""
    module_titles = soup_subpage.select('div.detailModule div.moduleTitle, div.normalModule div.moduleTitle')
    for title_div in module_titles:
        if '开放时间' == title_div.text.strip():
            content_div = title_div.find_next_sibling('div', class_='moduleContent')
            if content_div: return content_div.get_text(separator='; ', strip=True)
    items = soup_subpage.select('div.baseInfoModule div.baseInfoContent div.baseInfoItem')
    for item in items:
        title_element = item.select_one('p.baseInfoTitle')
        if title_element and '开放时间' in title_element.text:
            hours_element = item.select_one('p.baseInfoText.openTimeText span.openStatus')
            full_hours_text = item.select_one('p.baseInfoText.openTimeText')
            text_to_return = []
            if hours_element: text_to_return.append(hours_element.text.strip())
            if full_hours_text:
                raw_full_text = full_hours_text.text.strip()
                if hours_element and hours_element.text.strip() in raw_full_text:
                    raw_full_text = raw_full_text.replace(hours_element.text.strip(), "", 1).strip()
                text_to_return.append(raw_full_text.lstrip('；').strip())
            if text_to_return: return '；'.join(filter(None,text_to_return))
            generic_hours_element = item.select_one('p.baseInfoText')
            if generic_hours_element: return generic_hours_element.get_text(separator='; ', strip=True)
    return "N/A"

def extract_phone(soup_subpage):
    """Extract official phone number"""
    module_titles = soup_subpage.select('div.detailModule div.moduleTitle, div.normalModule div.moduleTitle')
    for title_div in module_titles:
        if '官方电话' == title_div.text.strip():
            content_div = title_div.find_next_sibling('div', class_='moduleContent')
            if content_div:
                phone_items = content_div.select('div.phoneItem span.phoneItemNum')
                if phone_items: return '; '.join([p.text.strip() for p in phone_items])
                return content_div.get_text(separator='; ', strip=True)
    phone_item_element = soup_subpage.select_one('div.baseInfoItem.baseInfoItemPhone span.phoneHeaderItem')
    if phone_item_element: return phone_item_element.text.strip().split('：')[-1].strip()
    items = soup_subpage.select('div.baseInfoModule div.baseInfoContent div.baseInfoItem')
    for item in items:
        title_element = item.select_one('p.baseInfoTitle')
        if title_element and ('官方电话' in title_element.text or '电话' in title_element.text):
            phone_text_container = item.select_one('div.baseInfoText.phoneHeaderBox div.phoneList')
            if phone_text_container:
                phone_spans = phone_text_container.select('span.phoneHeaderItem')
                if phone_spans: return '; '.join([span.text.strip().split('：')[-1].strip() for span in phone_spans])
            phone_text_direct = item.select_one('div.baseInfoText')
            if phone_text_direct: return phone_text_direct.get_text(separator='; ',strip=True).split('：')[-1].strip()
    return "N/A"

def extract_introduction(soup_subpage):
    intro_module_content = None
    module_titles = soup_subpage.select('div.detailModule div.moduleTitle, div.normalModule div.moduleTitle')
    for title_div in module_titles:
        if '介绍' in title_div.text.strip() and "景点介绍" in title_div.text.strip():
            intro_module_content = title_div.find_next_sibling('div', class_='moduleContent')
            break
        elif '介绍' == title_div.text.strip():
             intro_module_content = title_div.find_next_sibling('div', class_='moduleContent')
             break
    if not intro_module_content:
        for title_div in module_titles:
            if '介绍' in title_div.text.strip():
                intro_module_content = title_div.find_next_sibling('div', class_='moduleContent')
                break
    if intro_module_content:
        limit_height_div = intro_module_content.select_one('div.LimitHeightText div')
        if limit_height_div:
            text_parts = []
            for element in limit_height_div.children:
                if element.name == 'p': text_parts.append(element.get_text(strip=True))
            if text_parts: return '\n'.join(text_parts).strip()
        return intro_module_content.get_text(separator='\n', strip=True)
    return "N/A"

def extract_discount_policy(soup_subpage):
    policy_module_content = None
    module_titles = soup_subpage.select('div.detailModule div.moduleTitle, div.normalModule div.moduleTitle')
    for title_div in module_titles:
        if '优待政策' in title_div.text.strip():
            policy_module_content = title_div.find_next_sibling('div', class_='moduleContent')
            break
    if policy_module_content:
        rows = policy_module_content.select('div.moduleContentRow')
        if rows: return '\n'.join([row.get_text(separator=' ', strip=True) for row in rows])
        return policy_module_content.get_text(separator='\n', strip=True)
    return "N/A"

def extract_facilities(soup_subpage):
    facilities_module_content = None
    module_titles = soup_subpage.select('div.detailModule div.moduleTitle, div.normalModule div.moduleTitle')
    for title_div in module_titles:
        if '服务设施' in title_div.text.strip():
            facilities_module_content = title_div.find_next_sibling('div', class_='moduleContent')
            break
    if facilities_module_content:
        rows = facilities_module_content.select('div.moduleContentRow')
        if rows: return '\n\n'.join([row.get_text(separator=' ', strip=True) for row in rows])
        return facilities_module_content.get_text(separator='\n', strip=True)
    return "N/A"

# --- Main Function ---
if __name__ == "__main__":
    print("=" * 80)
    print("旅游景点信息爬虫脚本启动")
    print("=" * 80)
    print("目标: 爬取携程网成都景点信息")
    print(f"页面范围: 第{START_PAGE}页至第{END_PAGE}页")
    print(f"输出文件: {OUTPUT_CSV_FILE}")
    print("需要爬取的数据字段: 景点名称, 热度, 评分, 地址, 开放时间, 官方电话, 介绍, 优待政策, 服务设施, URL")
    print("=" * 80)
    
    print("正在导入并初始化必要模块...")
    driver = None
    start_time = time.time()  # 记录开始时间
    
    try:
        print("正在初始化Selenium WebDriver (无头模式)...")
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--disable-gpu')  # 禁用GPU加速
        chrome_options.add_argument('--no-sandbox')  # 禁用沙箱
        chrome_options.add_argument('--disable-dev-shm-usage')  # 避免内存问题
        chrome_options.add_argument('--ignore-certificate-errors')  # 忽略证书错误
        chrome_options.add_argument('--window-size=1920,1080')  # 设置窗口大小
        chrome_options.add_argument(f'user-agent={SUB_PAGE_HEADERS["User-Agent"]}')  # 设置用户代理
        # 添加更多选项以提高稳定性
        chrome_options.add_argument('--disable-extensions')  # 禁用扩展
        chrome_options.add_argument('--disable-browser-side-navigation')  # 禁用浏览器侧导航
        chrome_options.add_argument('--disable-features=NetworkService')  # 禁用网络服务
        driver = webdriver.Chrome(options=chrome_options)
        print("WebDriver初始化成功！")
    except Exception as e:
        print(f"Error initializing WebDriver: {e}")
        exit()
        
    all_attraction_data = []
    last_saved_page = START_PAGE - 1
    print(f"DEBUG: 脚本开始循环前, START_PAGE = {START_PAGE}, END_PAGE = {END_PAGE}")
    
    def save_temp_data(data, current_page):
        """保存临时数据到CSV文件"""
        try:
            with open(OUTPUT_TEMP_FILE, mode='w', newline='', encoding='utf-8-sig') as f:
                headers_csv = ["景点名称", "热度", "评分", "地址", "开放时间", "官方电话", "介绍", "优待政策", "服务设施", "URL"]
                writer = csv.DictWriter(f, fieldnames=headers_csv)
                writer.writeheader()
                writer.writerows(data)
                print(f"\n临时数据已保存至 {OUTPUT_TEMP_FILE}，当前进度：第 {current_page} 页")
        except Exception as e:
            print(f"保存临时数据时出错: {e}")
    
    try:
        for page_num in range(START_PAGE, END_PAGE + 1):
            current_list_url = PAGE_URL_TEMPLATE.format(page_num)
            print(f"\n--- 正在处理第 {page_num}/{END_PAGE} 页: {current_list_url} ---")
            
            # 定期保存数据，避免长时间运行后数据丢失
            if page_num - last_saved_page >= SAVE_INTERVAL:
                save_temp_data(all_attraction_data, page_num)
                last_saved_page = page_num
            retry_count = 0
            max_retries = 3  # 最大重试次数
            while retry_count < max_retries:
                try:
                    print(f"尝试加载页面 (尝试 {retry_count + 1}/{max_retries})...")
                    driver.get(current_list_url)
                    print(f"等待最多 {SELENIUM_WAIT_TIME} 秒加载列表容器 (class: list_wide_mod2)...")
                    WebDriverWait(driver, SELENIUM_WAIT_TIME).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "list_wide_mod2"))
                    )
                    print("主列表容器已找到，页面加载成功！")
                    page_source = driver.page_source
                    soup_main = BeautifulSoup(page_source, "html.parser")
                    attraction_list_container = soup_main.find("div", class_="list_wide_mod2")
                    if attraction_list_container:
                        break
                    else:
                        print("未找到景点列表容器，将重试...")
                        retry_count += 1
                        time.sleep(3)
                except Exception as e:
                    print(f"加载页面时出错: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"将在5秒后重试 ({retry_count}/{max_retries})...")
                        time.sleep(5)
                    else:
                        print(f"已达到最大重试次数 ({max_retries})，跳过此页面。")
                        break
            if retry_count >= max_retries:
                print(f"无法加载页面 {current_list_url}，继续处理下一页。")
                continue
                
            # 成功加载页面后，继续处理
            attraction_list_container = soup_main.find("div", class_="list_wide_mod2")

            if attraction_list_container:
                items_dt = attraction_list_container.find_all("dt")
                print(f"Found {len(items_dt)} potential attractions (dt elements) on page {page_num}.")

                for i, item_element in enumerate(items_dt):
                    a_tag = item_element.find("a", href=True)
                    if not a_tag:
                        continue
                    href_relative = a_tag.get('href')

                    if href_relative:
                        href_absolute = urljoin(current_list_url, href_relative)
                        if not href_absolute.startswith("http") or "/sight/" not in href_absolute or "/dianping/" in href_absolute or "#" in href_absolute:
                            continue
                        print(f"\n--- Processing Attraction {i + 1}/{len(items_dt)} from page {page_num} ---")
                        attraction_data = {
                            "景点名称": "N/A", "热度": "N/A", "评分": "N/A",
                            "地址": "N/A", "开放时间": "N/A", "官方电话": "N/A",
                            "介绍": "N/A", "优待政策": "N/A", "服务设施": "N/A",
                            "URL": href_absolute
                        }
                        soup_subpage_for_extraction = BeautifulSoup("", "html.parser")
                        try:
                            print(f"Selenium正在导航到子页面: {href_absolute}")
                            subpage_retry_count = 0
                            subpage_max_retries = 3
                            subpage_loaded = False
                            while subpage_retry_count < subpage_max_retries and not subpage_loaded:
                                try:
                                    driver.get(href_absolute)
                                    print(f"等待页面加载完成 ({subpage_retry_count + 1}/{subpage_max_retries})...")
                                    try:
                                        WebDriverWait(driver, SELENIUM_WAIT_TIME).until(
                                            EC.presence_of_any_elements_located((
                                                (By.CLASS_NAME, "baseInfoModule"),
                                                (By.CLASS_NAME, "titleView"),
                                                (By.CLASS_NAME, "detailModule")
                                            ))
                                        )
                                        subpage_loaded = True
                                        print("景点详情页面元素已加载")
                                    except Exception:
                                        print("无法找到期望的页面元素，使用延时等待...")
                                        time.sleep(SUBPAGE_NAV_DELAY)
                                        subpage_loaded = True
                                    subpage_source = driver.page_source
                                    soup_subpage_for_extraction = BeautifulSoup(subpage_source, "html.parser")
                                    print(f"已通过Selenium成功获取子页面 {href_absolute} 的源代码")
                                    break
                                except Exception as e_sub_retry:
                                    subpage_retry_count += 1
                                    print(f"访问子页面时出错: {e_sub_retry}")
                                    if subpage_retry_count < subpage_max_retries:
                                        print(f"将在3秒后重试 ({subpage_retry_count}/{subpage_max_retries})...")
                                        time.sleep(3)
                                    else:
                                        print(f"已达到子页面最大重试次数 ({subpage_max_retries})，使用空页面继续。")
                            # 调试: 保存第一个子页面的HTML以供检查
                            if not hasattr(extract_name, 'has_saved_first_selenium_subpage_html_v3'):
                                try:
                                    with open("debug_selenium_subpage_output.html", "w", encoding="utf-8") as f_debug:
                                        f_debug.write(subpage_source)
                                    print("已保存: 当前子页面的HTML已保存至 debug_selenium_subpage_output.html")
                                    extract_name.has_saved_first_selenium_subpage_html_v3 = True
                                except Exception as e_debug:
                                    print(f"保存调试HTML时出错: {e_debug}")
                        except Exception as e_sel_sub:
                            print(f"获取子页面 {href_absolute} 时出错: {e_sel_sub}")
                        print("开始提取景点信息...")
                        attraction_data["景点名称"] = extract_name(soup_subpage_for_extraction)
                        print(f"提取景点名称: {attraction_data['景点名称']}")
                        attraction_data["评分"] = extract_score(soup_subpage_for_extraction)
                        print(f"提取评分: {attraction_data['评分']}")
                        attraction_data["热度"] = extract_popularity(soup_subpage_for_extraction)
                        print(f"提取热度: {attraction_data['热度']}")
                        attraction_data["地址"] = extract_address(soup_subpage_for_extraction)
                        print(f"提取地址: {attraction_data['地址']}")
                        attraction_data["开放时间"] = extract_opening_hours(soup_subpage_for_extraction)
                        print(f"提取开放时间: {attraction_data['开放时间']}")
                        attraction_data["官方电话"] = extract_phone(soup_subpage_for_extraction)
                        print(f"提取官方电话: {attraction_data['官方电话']}")
                        attraction_data["介绍"] = extract_introduction(soup_subpage_for_extraction)
                        intro_display = attraction_data["介绍"][:50] + "..." if len(attraction_data["介绍"]) > 50 else attraction_data["介绍"]
                        print(f"提取介绍: {intro_display}")
                        attraction_data["优待政策"] = extract_discount_policy(soup_subpage_for_extraction)
                        policy_display = attraction_data["优待政策"][:50] + "..." if len(attraction_data["优待政策"]) > 50 else attraction_data["优待政策"]
                        print(f"提取优待政策: {policy_display}")
                        attraction_data["服务设施"] = extract_facilities(soup_subpage_for_extraction)
                        facilities_display = attraction_data["服务设施"][:50] + "..." if len(attraction_data["服务设施"]) > 50 else attraction_data["服务设施"]
                        print(f"提取服务设施: {facilities_display}")
                        print(f"已成功提取 {href_absolute} 的所有数据")
                        all_attraction_data.append(attraction_data)
            else:
                print(f"No attraction list container (div.list_wide_mod2) found on page {page_num}.")
            
            # 添加页面之间的延迟，避免请求过于频繁被识别为爬虫
            print(f"休息{PAGE_DELAY}秒后继续下一页...")
            time.sleep(PAGE_DELAY)

        # 数据写入CSV
        try:
            with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8-sig') as f:
                headers_csv = ["景点名称", "热度", "评分", "地址", "开放时间", "官方电话", "介绍", "优待政策", "服务设施", "URL"]
                writer = csv.DictWriter(f, fieldnames=headers_csv)
                writer.writeheader()
                writer.writerows(all_attraction_data)
                print(f"\nSuccessfully wrote {len(all_attraction_data)} attractions to {OUTPUT_CSV_FILE}")
        except Exception as e_csv:
            print(f"Error writing CSV file: {e_csv}")
    except Exception as e_main:
        print(f"Error in main process: {e_main}")
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed.")
    print("Script execution completed.")