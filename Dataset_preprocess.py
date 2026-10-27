import pandas as pd # 导入pandas库，用于数据处理和分析
import numpy as np # 导入numpy库，用于数值计算
import re # 导入re库，用于正则表达式操作
import os # 导入os库，用于与操作系统交互，例如文件路径操作

def clean_rating(rating_str): # 定义一个函数，用于清洗评分字符串
    """
    Cleans the rating string and converts it to a float.
    Example: "4.5分" -> 4.5
    """
    if pd.isna(rating_str) or str(rating_str).strip().upper() == "N/A" or str(rating_str).strip() == "": # 检查评分字符串是否为NaN、"N/A"或空字符串
        return np.nan # 如果是，则返回NaN
    # Try to extract a number, allowing for a decimal point
    match = re.search(r'(\d+\.?\d*)', str(rating_str)) # 尝试使用正则表达式提取数字（可能包含小数点）
    if match: # 如果匹配成功
        try:
            return float(match.group(1)) # 尝试将提取到的字符串转换为浮点数并返回
        except ValueError: # 如果转换失败
            return np.nan # 返回NaN
    return np.nan # 如果没有匹配到数字，也返回NaN

def clean_popularity(pop_str): # 定义一个函数，用于清洗热度字符串
    """
    Cleans the popularity string, handles units like 'w' or '万', and converts to a float.
    Example: "12.3w热度" -> 123000.0, "5000热度" -> 5000.0
    """
    if pd.isna(pop_str) or str(pop_str).strip().upper() == "N/A" or str(pop_str).strip() == "": # 检查热度字符串是否为NaN、"N/A"或空字符串
        return np.nan # 如果是，则返回NaN
    
    text = str(pop_str).lower() # 将热度字符串转换为小写
    num_val = None # 初始化数值变量
    
    # Check for 'w' or '万' (ten thousand)
    if 'w' in text or '万' in text: # 检查字符串中是否包含'w'或'万'
        match = re.search(r'(\d+\.?\d*)', text) # 尝试使用正则表达式提取数字
        if match: # 如果匹配成功
            try:
                num_val = float(match.group(1)) * 10000 # 将提取到的数字乘以10000（表示万）
            except ValueError: # 如果转换失败
                return np.nan # 返回NaN
    else: # If no 'w' or '万', try to extract number directly
        match = re.search(r'(\d+\.?\d*)', text) # 如果不包含'w'或'万'，直接尝试提取数字
        if match: # 如果匹配成功
            try:
                num_val = float(match.group(1)) # 将提取到的字符串转换为浮点数
            except ValueError: # 如果转换失败
                return np.nan # 返回NaN
    return num_val # 返回清洗后的数值

def extract_city(address_str): # 定义一个函数，用于从地址字符串中提取城市信息
    """
    Extracts city from address string.
    This function attempts to identify common Sichuan cities/regions.
    """
    if pd.isna(address_str) or address_str.strip() == "": # 检查地址字符串是否为NaN或空字符串
        return "" # 如果是，则返回空字符串

    address_str_norm = address_str.strip() # 去除地址字符串两端的空白字符

    # List of cities/regions to check for, ordered to avoid premature short matches
    # (e.g., check for "阿坝藏族羌族自治州" before just "阿坝")
    sichuan_entities = [ # 定义四川省的城市/地区列表，注意顺序以避免错误匹配
        "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州", # 自治州
        "成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", # 市
        "广元市", "遂宁市", "内江市", "乐山市", "南充市", "眉山市", "宜宾市", # 市
        "广安市", "达州市", "雅安市", "巴中市", "资阳市", # 市
        "都江堰市", "彭州市", "邛崃市", "崇州市", "广汉市", "什邡市", # 县级市
        "绵竹市", "江油市", "峨眉山市", "阆中市", "华蓥市", "万源市", # 县级市
        "简阳市", "西昌市", "康定市", "马尔康市", # 县级市
        # Add common county or district names if they often appear as the primary location identifier
        "锦江区", "青羊区", "金牛区", "武侯区", "成华区", "龙泉驿区", "青白江区", # 区
        "新都区", "温江区", "双流区", "郫都区", "新津区", "大邑县", "蒲江县", "金堂县", # 区/县
        "雨城区", "名山区", "东坡区", "彭山区", "仁寿县", "洪雅县", # 区/县
        "旌阳区", "罗江区", "中江县", "游仙区", "涪城区", "安州区", # 区/县
        "利州区", "昭化区", "朝天区", "船山区", "安居区", "东兴区", "翠屏区", "南溪区", # 区
        "顺庆区", "高坪区", "嘉陵区", "通川区", "达川区", "雁江区", "雨城区" # 区
    ]

    # Remove "四川省" or "四川" prefix if present
    if address_str_norm.startswith("四川省"): # 如果地址以"四川省"开头
        address_str_norm = address_str_norm[len("四川省"):].strip() # 去除"四川省"前缀并去除空白
    elif address_str_norm.startswith("四川"): # 如果地址以"四川"开头
        address_str_norm = address_str_norm[len("四川"):].strip() # 去除"四川"前缀并去除空白

    for entity in sichuan_entities: # 遍历四川省的城市/地区列表
        if address_str_norm.startswith(entity): # 如果地址以列表中的某个实体开头
            # Return the base name without suffix for consistency
            return re.sub(r'(市|县|区|自治州|藏族羌族自治州|彝族自治州)$', '', entity) # 返回去除后缀（如市、县、区等）的实体名称

    # Fallback for Chengdu if not caught by full "成都市"
    if address_str_norm.startswith("成都"): # 如果地址以"成都"开头（作为备选方案）
        return "成都" # 返回"成都"
        
    return "" # Return empty if no specific city is reliably extracted # 如果没有提取到特定城市，则返回空字符串


def main(): # 定义主函数
    script_dir = os.path.dirname(os.path.abspath(__file__)) # 获取当前脚本所在的绝对路径的目录部分

    input_csv_name = "完整数据爬取.csv" # 定义输入CSV文件的名称
    output_triplets_csv_name = "景点知识图谱_三元组.csv" # 定义输出三元组CSV文件的名称

    input_csv_path = os.path.join(script_dir, input_csv_name) # 构建输入CSV文件的完整路径
    output_triplets_csv_path = os.path.join(script_dir, output_triplets_csv_name) # 构建输出三元组CSV文件的完整路径
    
    # 由于输入和输出文件都与脚本在同一目录，
    # script_dir 必定存在，通常不需要为其调用 os.makedirs。
    # 如果输出文件需要存放到 script_dir 内的子目录（例如 "output"），
    # 则可以像这样创建：
    # output_dir = os.path.join(script_dir, "output")
    # os.makedirs(output_dir, exist_ok=True)
    # print(f"确保输出文件夹存在: {output_dir}")

    print(f"脚本运行目录: {script_dir}") # 打印脚本运行目录
    print(f"开始读取数据从: {input_csv_path}") # 打印开始读取数据的提示信息
    try:
        df = pd.read_csv(input_csv_path, encoding='utf-8-sig') # 尝试读取CSV文件，使用utf-8-sig编码以处理BOM头
    except FileNotFoundError: # 如果文件未找到
        print(f"错误: 文件未找到 {input_csv_path}") # 打印错误信息
        return # 结束函数执行
    except Exception as e: # 如果发生其他读取错误
        print(f"读取CSV文件时发生错误: {e}") # 打印错误信息
        return # 结束函数执行

    print(f"数据读取完毕，共 {len(df)} 条记录。开始预处理...") # 打印数据读取完成的提示信息和记录数

    # Apply cleaning and create numerical columns
    df["评分_数值"] = df["评分"].apply(clean_rating) if "评分" in df.columns else np.nan # 如果存在"评分"列，则应用clean_rating函数创建"评分_数值"列，否则填充NaN
    df["热度_数值"] = df["热度"].apply(clean_popularity) if "热度" in df.columns else np.nan # 如果存在"热度"列，则应用clean_popularity函数创建"热度_数值"列，否则填充NaN

    # Ensure essential text columns exist, fill with empty string if not, then process
    text_cols_to_ensure = ["景点名称", "地址", "开放时间", "官方电话", "介绍", "优待政策", "服务设施", "URL"] # 定义需要确保存在的文本列列表
    for col in text_cols_to_ensure: # 遍历列表中的每一列
        if col not in df.columns: # 如果该列不在DataFrame的列中
            df[col] = "" # 创建该列并用空字符串填充
            print(f"警告: 列 '{col}' 未在CSV中找到，已创建为空列。") # 打印警告信息

    # Standardize N/A and strip whitespace for all object columns (or columns we treat as text)
    for col in df.columns: # 遍历DataFrame的所有列
        if df[col].dtype == 'object' or col in text_cols_to_ensure : # 如果列的数据类型是object或者在text_cols_to_ensure列表中
            df[col] = df[col].astype(str).str.strip() # 将列转换为字符串类型并去除两端空白
            df[col] = df[col].replace({"N/A": np.nan, "nan": np.nan, "": np.nan, "None": np.nan}) # 将"N/A", "nan", 空字符串, "None"替换为NaN


    triplets = [] # 初始化一个空列表，用于存储三元组
    print("开始生成三元组...") # 打印开始生成三元组的提示信息
    unique_attraction_names = set() # 初始化一个空集合，用于存储唯一的景点名称

    for index, row in df.iterrows(): # 遍历DataFrame的每一行
        subject_name = row.get("景点名称") # 获取当前行的"景点名称"

        if pd.isna(subject_name) or str(subject_name).strip() == "": # 如果景点名称为NaN或空字符串
            # print(f"第 {index+2} 行因景点名称缺失已跳过。") # +2 because of header and 0-indexing # 打印跳过信息（注释掉了）
            continue # 跳过当前循环，处理下一行

        subject_name = str(subject_name).strip() # 将景点名称转换为字符串并去除两端空白
        unique_attraction_names.add(subject_name) # 将景点名称添加到唯一景点名称集合中

        # 1. 地点相关 (地址)
        address = row.get("地址") # 获取当前行的"地址"
        if pd.notna(address) and str(address).strip() != "": # 如果地址不为NaN且不为空字符串
            address_clean = str(address).strip() # 清洗地址字符串
            triplets.append({"subject": subject_name, "predicate": "位于", "object": address_clean}) # 添加"景点名称 位于 地址"的三元组
            # 1a. 地点相关 (城市)
            city = extract_city(address_clean) # 从清洗后的地址中提取城市信息
            if city and city.strip() != "": # 如果提取到的城市不为空
                triplets.append({"subject": subject_name, "predicate": "属于城市", "object": city.strip()}) # 添加"景点名称 属于城市 城市"的三元组
        
        # 2. 评价相关 (评分)
        rating_value = row.get("评分_数值") # 获取当前行的"评分_数值"
        if pd.notna(rating_value): # 如果评分数值不为NaN
            triplets.append({"subject": subject_name, "predicate": "的评分是", "object": rating_value}) # 添加"景点名称 的评分是 评分数值"的三元组

        # 3. 评价相关 (热度)
        popularity_value = row.get("热度_数值") # 获取当前行的"热度_数值"
        if pd.notna(popularity_value): # 如果热度数值不为NaN
            triplets.append({"subject": subject_name, "predicate": "的热度为", "object": popularity_value}) # 添加"景点名称 的热度为 热度数值"的三元组

        # 4. 时间相关 (开放时间)
        opening_hours = row.get("开放时间") # 获取当前行的"开放时间"
        if pd.notna(opening_hours) and str(opening_hours).strip() != "": # 如果开放时间不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的开放时间为", "object": str(opening_hours).strip()}) # 添加"景点名称 的开放时间为 开放时间"的三元组

        # 5. 联系方式相关 (官方电话)
        phone = row.get("官方电话") # 获取当前行的"官方电话"
        if pd.notna(phone) and str(phone).strip() != "": # 如果官方电话不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的官方电话是", "object": str(phone).strip()}) # 添加"景点名称 的官方电话是 官方电话"的三元组
            
        # 6. 介绍相关 (介绍)
        introduction = row.get("介绍") # 获取当前行的"介绍"
        if pd.notna(introduction) and str(introduction).strip() != "": # 如果介绍不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的介绍是", "object": str(introduction).strip()}) # 添加"景点名称 的介绍是 介绍"的三元组

        # 7. 优待政策相关 (优待政策)
        discount_policy = row.get("优待政策") # 获取当前行的"优待政策"
        if pd.notna(discount_policy) and str(discount_policy).strip() != "": # 如果优待政策不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的优待政策是", "object": str(discount_policy).strip()}) # 添加"景点名称 的优待政策是 优待政策"的三元组

        # 8. 服务设施相关 (服务设施)
        facilities = row.get("服务设施") # 获取当前行的"服务设施"
        if pd.notna(facilities) and str(facilities).strip() != "": # 如果服务设施不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的服务设施包括", "object": str(facilities).strip()}) # 添加"景点名称 的服务设施包括 服务设施"的三元组

        # 9. 网络资源相关 (URL)
        url_link = row.get("URL") # 获取当前行的"URL"
        if pd.notna(url_link) and str(url_link).strip() != "": # 如果URL不为NaN且不为空字符串
            triplets.append({"subject": subject_name, "predicate": "的URL是", "object": str(url_link).strip()}) # 添加"景点名称 的URL是 URL"的三元组

    triplets_df = pd.DataFrame(triplets) # 将三元组列表转换为DataFrame
    print(f"已生成 {len(triplets_df)} 条三元组。") # 打印生成的三元组数量

    if not triplets_df.empty: # 如果三元组DataFrame不为空
        print(f"三元组示例:\n{triplets_df.head()}") # 打印三元组的前5行作为示例
    else: # 如果三元组DataFrame为空
        print("未能生成任何三元组，请检查输入数据和处理逻辑。") # 打印未能生成三元组的提示


    print(f"预处理和三元组生成完成，保存数据到: {output_triplets_csv_path}") # 打印预处理和三元组生成完成的提示信息
    try:
        triplets_df.to_csv(output_triplets_csv_path, index=False, encoding='utf-8-sig') # 尝试将三元组DataFrame保存到CSV文件，不包含索引，使用utf-8-sig编码
        print(f"数据成功保存到 {output_triplets_csv_path}。") # 打印数据成功保存的提示信息
    except Exception as e: # 如果保存CSV文件时发生错误
        print(f"保存CSV文件时发生错误: {e}") # 打印错误信息

    # --- 新增：保存景点名称到dict/attraction_name.txt ---
    if unique_attraction_names: # 如果唯一景点名称集合不为空
        dict_dir = os.path.join(script_dir, 'dict') # 构建存放词典文件的目录路径
        if not os.path.exists(dict_dir): # 如果目录不存在
            os.makedirs(dict_dir) # 创建目录
            print(f"创建文件夹: {dict_dir}") # 打印创建文件夹的提示信息

        attraction_dict_path = os.path.join(dict_dir, 'attraction_name.txt') # 构建景点名称词典文件的完整路径
        sorted_attraction_names = sorted(list(unique_attraction_names)) # 将唯一景点名称集合转换为列表并排序
        
        try:
            with open(attraction_dict_path, 'w', encoding='utf-8') as f: # 尝试以写入模式打开词典文件，使用utf-8编码
                for name in sorted_attraction_names: # 遍历排序后的景点名称列表
                    f.write(name + '\n') # 将每个景点名称写入文件，并添加换行符
            print(f"已将 {len(sorted_attraction_names)} 个唯一景点名称保存到 {attraction_dict_path}") # 打印保存成功的提示信息和数量
        except Exception as e: # 如果保存词典文件时发生错误
            print(f"保存景点名称词典到 {attraction_dict_path} 时发生错误: {e}") # 打印错误信息
    else: # 如果唯一景点名称集合为空
        print("未能提取到任何唯一的景点名称，未生成景点词典文件。") # 打印未能提取到唯一景点名称的提示
    # --- 新增代码结束 ---

if __name__ == "__main__": # 如果当前脚本是主程序运行
    main() # 调用main函数