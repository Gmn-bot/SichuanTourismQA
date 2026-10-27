# 四川旅游 ReAct 智能体 + GraphRAG

> 本分支是 **v3：ReAct 智能体 + Neo4j GraphRAG**。三个版本历史互不合并，不要混在一起：
>
> | 分支 | 版本 | 说明 |
> | --- | --- | --- |
> | [`main`](https://github.com/Gmn-bot/SichuanTourismQA/tree/main) | v1 | 旧规则问答（Flask / py2neo / 讯飞星火） |
> | [`graphrag`](https://github.com/Gmn-bot/SichuanTourismQA/tree/graphrag) | v2 | GraphRAG 流水线（规则理解 + 图谱检索 + 生成） |
> | [`agent`](https://github.com/Gmn-bot/SichuanTourismQA/tree/agent) | v3 | 本分支：单智能体 ReAct 选工具，图谱作为工具附属 |

基于 Neo4j 知识图谱的 **文旅咨询助手**：有 API Key 时，LangChain ReAct 智能体选择工具查询图谱（票价/天气/购票渠道也走工具）；无 Key 时走规则理解 + 模板。余票没有库存接口时如实说明，不编剩余张数。

设计说明：[docs/OPTIMIZATION.md](docs/OPTIMIZATION.md)

## 环境

- Python 3.10+
- Neo4j 5+（Desktop 或社区版，Bolt `7687`）

```bash
conda activate youhua
pip install -r requirements.txt
copy .env.example .env
```

在 `.env` 填写 `NEO4J_PASSWORD` 和可选的 `LLM_API_KEY`（火山方舟 DeepSeek V4）。

Neo4j Desktop 里把实例点 Start，然后：

```bash
python run.py import
python run.py chat
python run.py web
```

浏览器打开 **http://127.0.0.1:5000**（不要用 `0.0.0.0`）。

```bash
python run.py eval
python -m unittest tests.test_enricher tests.test_nlu_graph tests.test_offline tests.test_agent
```

评测默认关闭 LLM，衡量图谱检索 + 模板；报告写入 [data/eval/latest.json](data/eval/latest.json)，摘要见 [docs/EVAL.md](docs/EVAL.md)。加 `--llm` 才走 DeepSeek V4。

## 问答链路

```
问题 → ReAct 智能体（思考 → 选工具 → 观察 → 不够再调）
    → 工具内部 GraphRAG：按名 Cypher · 城市/标签推荐 · 全文 · NEAR
    → 票价/天气/余票：lookup_ticket_price · get_weather · lookup_booking_status（官网入口，不编库存）
    → 按证据生成 + 来源卡片 + 思考/行动轨迹
无 Key 时：Gazetteer + QueryPlan → 同一套检索 → 模板
```

图谱标签：`Attraction` `City` `Tag` `Facility`；关系：`IN_CITY` `HAS_TAG` `HAS_FACILITY` `NEAR`。

## 命令

| 命令 | 作用 |
|------|------|
| `python run.py import` | 三元组导入 Neo4j，并打标签 / 设施 / 是否免费 / NEAR |
| `python run.py chat` | 终端问答 |
| `python run.py web` | FastAPI 网页（`/api/ask`、`/health`） |
| `python run.py eval` | 黄金集评测 |

## 目录

```
run.py                     CLI 入口
src/sichuan_qa/            问答、图谱、检索、生成、API
templates/chat.html        对话页
data/eval/golden.json      黄金集
dict/attraction_name.txt   景点词典
景点知识图谱_三元组.csv      导入数据
docs/OPTIMIZATION.md       设计
```

数据已在仓库中。若要重爬：`ctrip_crawler.py` → `Dataset_preprocess.py`。
