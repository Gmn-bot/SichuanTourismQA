# 四川旅游知识图谱问答系统

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

## 项目概述

四川旅游知识图谱问答系统是一个基于知识图谱和大语言模型的混合问答系统，专注于提供四川省内旅游景点相关信息。系统首先尝试从本地Neo4j知识图谱中查询答案，当无法获得满意结果时，会自动调用讯飞星火大模型API进行补充回答，为用户提供全面、准确的旅游信息服务。

## 快速开始

### 环境准备
```bash
# 克隆代码仓库
git clone https://github.com/Blue-OldMan/SichuanTourismQA.git
cd SichuanTourismQA

# 创建并激活虚拟环境
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境
copy .env.example .env
# 编辑.env文件，填入Neo4j和API配置
```

### 导入数据
```bash
# 导入知识图谱数据到Neo4j
python src/main.py import
```

### 启动系统
```bash
# 启动Web服务
python src/main.py web

# 或者使用命令行交互模式
python src/main.py chat
```

## 系统架构

系统主要由以下几个核心模块组成：

### 1. 数据获取与预处理模块

- **数据爬取**：`ctrip_crawler.py` 用于从携程网站爬取四川景点信息
- **数据预处理**：`Dataset_preprocess.py` 用于清洗原始数据并转换为知识图谱三元组格式

### 2. 知识图谱构建模块

- **数据导入**：`py2neo_data_import.py` 用于将三元组数据导入Neo4j数据库

### 3. 问答系统模块

- **问题分类器**：`question_classifier.py` 用于识别用户问题类型和提取关键实体
  - **实体识别技术**：
    - 采用 Aho-Corasick 自动机算法实现 O(n+k+z) 时间复杂度的多模式字符串匹配，其中 n 为输入文本长度，k 为模式总长度，z 为匹配结果数
    - 通过 `build_actree` 方法构建字典树，用于高效识别问题中的景点名称
    - 支持最长匹配策略，解决实体嵌套问题，例如"成都大熊猫基地"与"熊猫基地"的识别优先级
  - **问题分类逻辑**：
    - 采用基于规则的分层分类策略，先确认是否含有景点实体，再判断具体问题类型
    - 使用特征词集合（如 `address_qwds`, `opening_hours_qwds`）匹配问题意图
    - 设计默认问题类型处理机制，将未匹配到具体类型但含有景点的问题归类为"简介"查询
  - **简称处理机制**：
    - 维护 `attraction_aliases` 字典，支持"熊猫基地"到"成都大熊猫繁育研究基地"的映射
    - 在 `extract_entities` 方法中优化实体提取，将识别到的简称转换为全称

- **问题解析器**：`question_parser.py` 用于将分类结果转换为Cypher查询语句
  - **数据结构转换**：
    - 通过 `build_entitydict` 方法将 `{'实体': ['类型']}` 转换为 `{'类型': ['实体1', '实体2']}` 格式
    - 此转换简化了后续对同一类型多实体的批量处理
  - **查询语句生成**：
    - 为每种问题类型（地址、开放时间、电话等）定制专用的Cypher查询模板
    - 使用列表推导式高效生成多个实体的查询：`[f"MATCH (a:景点) WHERE a.name = '{entity}' RETURN a.name, a.address" for entity in entities]`
    - 在返回结果中使用 AS 语句设置标准化别名，便于答案搜索器处理
  - **查询类型扩展**：
    - 支持7种基本问题类型：地址、开放时间、电话、评分、热度、官网、门票价格、简介
    - 保留了扩展接口，便于未来添加更复杂的图数据库查询（如关系查询）

- **答案搜索器**：`answer_search.py` 实现了 RAG (检索增强生成) 的核心流程，通过从知识图谱检索答案并增强生成自然语言回复
  - **数据库交互**：
    - 使用 py2neo 库连接 Neo4j 图数据库，通过 `self.g = Graph(uri="bolt://localhost:7687", auth=("neo4j", "neo4j"))` 初始化连接
    - 在 `search_main` 方法中封装了查询执行逻辑，支持异常处理和日志记录
  - **查询执行流程**：
    - 接收 `parser_main` 生成的多组查询语句，批量执行并聚合结果
    - 通过 `self.g.run(query).data()` 执行Cypher查询并获取数据格式化结果
    - 实现了查询失败的容错处理，通过 try-except 机制捕获和处理异常
  - **答案美化与生成**：
    - `answer_prettify` 方法根据问题类型应用不同的自然语言模板
    - 使用条件逻辑处理各种情况，包括空值、格式异常和数据缺失
    - 通过 `final_answer_parts.append(f"{subject_name}的地址是：{value}。")` 等模板构建自然语言回答
  - **缺失信息处理**：
    - 实现了多层级的回退策略，当无法找到答案时给出友好提示
    - 尝试从查询中提取实体名称，提供针对性的回复：`f"抱歉，没有找到关于"{entity_name}"的"{question_type}"信息。"`
    - 为不同类型的查询失败提供不同的错误信息，提升用户体验

- **API接入**：`Backend_code.py` 中集成的讯飞星火API作为知识图谱的补充
    - **目的**：当本地知识图谱无法找到答案或问题不涉及特定图谱实体时，调用外部大语言模型API作为补充，以提供更广泛的回答能力。
    - **集成服务**：系统集成了**讯飞星火认知大模型 API (Spark X1)**。
    - **通信方式**：通过 **WebSocket** 与讯飞星火API进行实时双向通信，以获取流式响应。
    - **认证机制**：API的访问需要配置`APPID`, `APIKEY`, 和 `APISECRET`进行 HMAC-SHA256 签名认证。相关认证参数和URL生成逻辑位于 `Backend_code.py` 中的 `generate_auth_params` 函数。
    - **调用逻辑**：在 `Backend_code.py` 的 `get_tourist_answer` 函数中，当知识图谱无法提供答案时（例如，未识别出实体、无法构建查询或查询无结果），系统会调用 `get_answer_from_api` 函数，该函数进一步通过 `run_spark_x1_websocket` 与讯飞星火API交互。
    - **上下文管理**：API调用时会传递用户的对话历史（`chat_history`），以便大模型能够理解上下文，提供更连贯的回答。

### 4. Web界面

- **后端服务**：`Backend_code.py` 使用Flask框架提供Web服务
- **前端界面**：`templates/index.html` 提供简洁直观的用户交互界面

## 系统流程

1. 用户通过Web界面输入旅游相关问题
2. 系统对问题进行分类，识别问题意图和相关景点实体
3. 首先尝试从本地知识图谱查询答案：
   - 如果识别出景点实体且查询到答案，直接返回结果
   - 如果无法识别景点实体、无法构建查询语句或知识图谱中没有相关信息，则调用API
4. 调用讯飞星火API获取答案，并维护对话上下文
5. 将结果呈现给用户

## 功能特点

- **混合式问答**：结合知识图谱的精准答案和大语言模型的灵活性
- **语义理解**：能够准确理解用户提问意图，匹配相关景点
- **多维度信息**：支持查询景点地址、开放时间、门票价格、评分、简介等多维度信息
- **上下文记忆**：通过会话历史管理，保持对话连贯性
- **易于扩展**：模块化设计便于添加新的功能和知识

## 环境要求

- Python 3.8+
- Neo4j 4.0+
- 讯飞星火API账号（需要APPID、APIKEY和APISECRET）

## 依赖库

```
flask
py2neo
websocket-client
beautifulsoup4
selenium
pandas
numpy
```

## 安装与部署

1. 克隆或下载项目代码

2. 安装依赖库
   ```
   pip install flask py2neo websocket-client beautifulsoup4 selenium pandas numpy
   ```

3. 安装和配置Neo4j数据库
   - 从[Neo4j官网](https://neo4j.com/download/)下载并安装Neo4j
   - 创建一个新数据库，设置用户名和密码
   - 在`py2neo_data_import.py`和`answer_search.py`中更新数据库连接信息

4. 配置讯飞星火API
   - 注册[讯飞开放平台](https://www.xfyun.cn/)账号并创建应用
   - 在`Backend_code.py`中更新APPID、APIKEY和APISECRET

5. 数据导入
   ```
   python Dataset_preprocess.py  # 处理爬取的数据
   python py2neo_data_import.py  # 将三元组数据导入Neo4j
   ```

6. 启动系统
   ```
   python Backend_code.py
   ```

7. 访问系统
   在浏览器中访问 http://localhost:5000

## 使用示例

1. **基本景点信息查询**
   - "武侯祠的地址在哪里？"
   - "九寨沟的开放时间是什么？"
   - "都江堰的门票多少钱？"

2. **景点评价查询**
   - "峨眉山的评分是多少？"
   - "乐山大佛的热度怎么样？"

3. **开放式问题**
   - "推荐成都有哪些著名景点？"
   - "四川有哪些适合冬季旅游的地方？"
   - "春节期间去九寨沟需要注意什么？"

## 项目结构

```
SichuanTourismQA/
├── src/                   # 源代码目录
│   ├── main.py            # 主程序入口
│   ├── api/               # API服务
│   ├── data/              # 数据处理
│   ├── models/            # 核心模型
│   └── utils/             # 工具函数
│       ├── config.py      # 配置管理
│       ├── logger.py      # 日志工具
│       ├── database.py    # 数据库工具
│       └── api.py         # API工具
├── data/                  # 数据文件
│   └── 景点知识图谱_三元组.csv # 知识图谱数据
├── dict/                  # 词典目录
│   └── attraction_name.txt # 景点名称词典
├── templates/             # 前端模板
│   └── index.html         # 主页面
├── tests/                 # 测试代码
│   ├── test_classifier.py # 分类器测试
│   ├── test_parser.py     # 解析器测试
│   └── test_searcher.py   # 搜索器测试
├── Backend_code.py        # 后端Web服务
├── tourist_qa_main.py     # 问答系统主程序
├── question_classifier.py # 问题分类器
├── question_parser.py     # 问题解析器
├── answer_search.py       # 答案搜索器
├── ctrip_crawler.py          # 数据爬取程序
├── Dataset_preprocess.py  # 数据预处理程序
├── py2neo_data_import.py  # 数据导入Neo4j程序
├── setup.py               # 安装脚本
├── .gitignore             # Git忽略文件
├── .env.example           # 环境变量模板
├── DEPLOYMENT.md          # 部署指南
├── REFACTORING.md         # 重构建议
├── requirements.txt       # 依赖包列表
├── LICENSE                # 开源许可证
└── README.md              # 项目文档
```

## 命令行工具

项目提供了命令行工具，方便执行各种操作：

```bash
# 启动Web服务
python src/main.py web [--host HOST] [--port PORT] [--debug]

# 开始命令行聊天
python src/main.py chat

# 导入知识图谱数据
python src/main.py import [--file FILE_PATH] [--clear]

# 爬取新的旅游数据
python src/main.py crawl [--output OUTPUT_PATH] [--limit LIMIT]

# 运行测试
python src/main.py test [--module MODULE_NAME]
```

## 项目研究内容

本项目主要围绕以下几个方面进行研究：

1.  **特定领域知识图谱构建技术研究**：
    *   研究如何高效、准确地从多源异构数据（如旅游网站）中获取四川旅游相关的实体、属性和关系。
    *   探索数据清洗、预处理、知识建模（定义实体类型、关系类型）以及图数据库（Neo4j）的存储与管理技术。

2.  **面向旅游领域的自然语言理解技术研究**：
    *   **意图识别**：研究如何准确判断用户查询意图，例如查询景点地址、开放时间、门票价格或寻求景点推荐等。
    *   **实体识别与链接**：研究如何从用户问题中准确识别四川旅游实体（如“武侯祠”、“九寨沟”），并将其链接到知识图谱中对应的节点，包括对Aho-Corasick算法的应用和景点简称的处理。

3.  **基于知识图谱的问答生成与检索增强技术研究**：
    *   **查询转换**：研究如何将用户自然语言问题准确转换为知识图谱可执行的查询语言（如Cypher）。
    *   **答案生成与美化**：研究如何从知识图谱查询结果中提取核心信息，并以自然、友好的语言风格呈现给用户。
    *   **检索增强生成 (RAG)**：探索当本地知识图谱无法直接回答时，如何有效地结合外部大语言模型（讯飞星火）的能力，通过检索图谱信息来增强大模型的回答质量，实现知识图谱与大模型的协同工作。

4.  **混合问答系统架构设计与优化研究**：
    *   研究如何设计一个高效、鲁棒的混合问答系统架构。
    *   探索系统在本地知识图谱查询和外部API调用之间的智能切换与补充机制。
    *   研究对话上下文管理方法，以提供流畅的多轮交互体验。

5.  **旅游信息服务应用研究**：
    *   探索知识图谱问答系统在实际旅游信息服务场景中的应用价值，例如提供精准的景点信息查询、辅助行程规划、实现个性化旅游推荐等。

## 技术亮点

1. **多源融合**：结合结构化知识图谱与非结构化大语言模型，取长补短
2. **分层架构**：问题理解、查询构建、答案生成的清晰分层设计
3. **灵活回退**：当知识图谱无法满足需求时，智能切换到API查询
4. **会话管理**：维护用户会话上下文，实现连续对话
5. **可扩展性**：易于扩展新的问题类型和实体关系

## 未来展望

1. **丰富知识图谱**：增加更多四川旅游景点信息和关系类型
2. **优化问题理解**：引入更先进的NLP技术提升问题意图识别和实体提取精度
3. **多模态支持**：添加图像识别功能，支持用户上传景点照片进行查询
4. **个性化推荐**：基于用户兴趣和历史记录提供个性化旅游推荐
5. **多语言支持**：增加英语等多语言支持，服务国际游客

## 致谢

感谢所有为本项目提供支持的数据来源、开源库和技术文档。特别感谢讯飞开放平台提供的星火大模型API支持。

## 许可证

本项目采用 MIT 许可证。
