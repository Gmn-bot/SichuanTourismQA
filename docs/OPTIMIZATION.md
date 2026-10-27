# 四川旅游问答系统：GraphRAG 优化方案（实施版）

> 状态：P0–P6 已落地（导入、增强、混合检索、推荐排序、FastAPI、黄金集评测）。P7 向量 / Text2Cypher / LLM 重标为可选。仓库只保留 GraphRAG。

---

## 0. 一句话目标

用 Neo4j 存四川景点知识（实体、属性、关系），用 LangChain 编排「理解 → 混合检索 → 带出处生成」。  
事实问题走约束 Cypher，推荐/开放问题走全文/向量 + 一跳图扩展。生成只允许基于检索上下文。

---

## 1. 现状诊断（为什么必须改）

| 维度 | 现状 | 问题 |
|------|------|------|
| NLU | Aho-Corasick + 关键词 8 类 | 问法稍变就失败；无实体就整段丢给大模型 |
| 图谱 | 景点节点 + 属性，关系只有 `属于城市` | 名为知识图谱，实为属性表；城市边、设施字段未用于问答 |
| 查询 | 字符串拼接 Cypher | 注入风险；门票误查 `discountPolicy` |
| 生成 | 固定模板；失败调星火 | 星火看不到图谱，等于两套系统 |
| 工程 | 根目录脚本 + 空 `src/` | 双轨、`.env` 路径错误、`requirement.txt` 文件名不一致 |
| 导入 | `SET s.{{prop_key}}` | f-string 把属性名写成字面量，节点可能没有属性 |
| 评测 | 3 个单测，无问答质量数字 | 简历无法证明「变好了」 |

面试官会问的三句话，现状都答不上：

1. 图结构解决了纯向量解决不了的什么问题？  
2. 多跳 / 多约束查询怎么走？  
3. 幻觉和错误 Cypher 怎么防、怎么测？

---

## 2. 目标与非目标

### 做

- 英文标签的可 Text2Cypher schema（节点 + 多种关系，不再是属性袋）
- 离线增强：标签、设施、是否免费/票价线索、同城相关边
- LangChain LCEL 编排混合检索 RAG
- 查询理解输出 **结构化 QueryPlan**，Python 映射到 Cypher 模板（默认禁止自由生成 Cypher）
- FastAPI + 带出处的对话页
- 黄金集评测：事实 / 推荐 Hit / 拒答 / 延迟（不再对照已删除的旧规则基线）
- 官方 `neo4j` 驱动替代已停止维护的 py2neo
- LLM 可插拔（DeepSeek / 通义 / 星火 OpenAI 兼容网关 / 本地），不绑死一家

### 不做

- 五角色 LangGraph 多智能体
- 微调大模型（2000 条不够，也不是瓶颈）
- 把爬虫当重构主体
- 无约束 `GraphCypherQAChain` 让模型随便写 Cypher
- 旧规则问答基线（已删除，仓库只留 GraphRAG）

---

## 3. 目标架构

```
                    ┌─────────────────────────────────────┐
                    │            FastAPI / CLI            │
                    └─────────────────┬───────────────────┘
                                      │ question
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  Query Understanding (LangChain)    │
                    │  LLM → QueryPlan；失败则规则回退    │
                    │  词典 AC 只做实体 gazetteer         │
                    └─────────────────┬───────────────────┘
                                      │ QueryPlan
                                      ▼
                    ┌─────────────────────────────────────┐
                    │         Hybrid Graph Retriever      │
                    │  ① 约束 Cypher（事实 / 多约束）      │
                    │  ② 全文索引（开放问法）              │
                    │  ③ 一跳扩展 IN_CITY / HAS_TAG / NEAR│
                    │  ④ 可选向量（简介 embedding）        │
                    └─────────────────┬───────────────────┘
                                      │ Evidence (triples + text)
                                      ▼
                    ┌─────────────────────────────────────┐
                    │     Grounded Generation (LCEL)      │
                    │  只根据 Evidence 生成；无证据则拒答  │
                    │  无 LLM key 时退回模板成句           │
                    └─────────────────────────────────────┘
                                      │
                                      ▼
                               answer + sources
```

路由规则：

| QueryPlan.intent | 检索 |
|------------------|------|
| `fact` | 实体 + 属性，参数化 `MATCH (a:Attraction {name:$name}) RETURN ...` |
| `intro` | 实体简介 + 标签/城市/设施 |
| `recommend` | 城市 + 标签 + 评分过滤 + NEAR |
| `compare` | 两个以上实体的属性并排 |
| `open` | 全文/向量 TopK + 一跳邻居；仍不编造库外事实 |

---

## 4. 知识图谱 Schema

旧图标签是中文 `景点`/`城市`，LLM 写 Cypher 不稳定。新图 **重建为英文标签**（导入时 `--clear`）。

### 4.1 节点

**Attraction**

| 属性 | 类型 | 来源 |
|------|------|------|
| name | string, unique | 景点名称 |
| address | string | 位于 |
| rating | float | 的评分是 |
| popularity | float | 的热度为 |
| opening_time | string | 的开放时间为 |
| phone | string | 的官方电话是 |
| introduction | string | 的介绍是 |
| discount_policy | string | 的优待政策是 |
| website | string | 的URL是 |
| ticket_info | string | 从优待政策抽取 |
| is_free | bool | 规则：名称/政策含「免费」等 |
| facilities_text | string | 原始服务设施文本 |

**City** `{name}`  
**Tag** `{name}`  如 人文 / 自然 / 亲子 / 历史 / 游乐 / 免费 / 高分 / 热门  
**Facility** `{name}`  停车场、餐饮、卫生间等

### 4.2 关系

```
(Attraction)-[:IN_CITY]->(City)
(Attraction)-[:HAS_TAG]->(Tag)
(Attraction)-[:HAS_FACILITY]->(Facility)
(Attraction)-[:NEAR {reason: "same_city_tag"}]->(Attraction)
```

### 4.3 约束与索引

- `Attraction.name` UNIQUE  
- `City.name` / `Tag.name` / `Facility.name` UNIQUE  
- 全文：`Attraction(name, introduction, address)`  
- 可选向量：`Attraction.embedding`

### 4.4 图如何回答「向量不好答」的问题

- 「成都适合带小孩、评分 4.5 以上」→ `IN_CITY` + `HAS_TAG:亲子` + `rating` 过滤  
- 「去了武侯祠还能去哪」→ `NEAR` / 同城同标签  
- 「九寨沟和黄龙哪个更适合冬季」→ 两节点属性 + 简介证据，禁止空口对比

没有这些边，GraphRAG 就是套壳，禁止跳过增强阶段。

---

## 5. 数据增强（离线，导入时完成）

不在问答热路径上调 LLM 抽标签。

1. **设施**：按换行、分号、顿号切开 `服务设施`，取 `：` 前的设施名，过滤过短噪声。  
2. **标签**：只在景点名上正则（熊猫→亲子/自然/动物，寺祠→人文/历史，山湖沟→自然/户外，乐园→游乐/亲子…）；`rating>=4.5`→高分；政策含免费→免费。简介不参与打标，避免「跳伞店简介提到熊猫」被标成亲子。  
3. **票价线索**：正则抽「免费 / 成人票 N 元」；抽不到则 `ticket_info` 留空，问答必须说「库中无票价」。  
4. **NEAR**：同城、共享至少 1 个标签、按评分取 Top 3（无标签则同城高分 Top 3）。  

2000 条全部规则可完成；后续可用 LLM 离线重标，接口预留 `enrich --llm`。

---

## 6. 查询理解

输出严格 schema（Pydantic）：

```python
class QueryPlan(BaseModel):
    intent: Literal["fact", "intro", "recommend", "compare", "open"]
    entities: list[str]          # 对齐到 Attraction.name
    city: str | None
    tags: list[str]
    attributes: list[str]        # address/phone/opening_time/...
    raw_question: str
```

流程：

1. Gazetteer（Aho-Corasick + 简称表 + 最长匹配）给出实体候选  
2. 有 LLM：把问题、候选实体、标签词表交给模型，产出 QueryPlan  
3. 无 LLM 或解析失败：关键词意图（沿用并收紧原 8 类）+ 城市词表  

实体链接只允许落在词典/图中已有名称，禁止模型发明景点。

---

## 7. 混合检索（GraphRAG 的实际含义）

检索器返回 `Evidence`：

```python
class EvidenceItem(BaseModel):
    name: str
    properties: dict
    city: str | None
    tags: list[str]
    neighbors: list[str]
    snippet: str | None
    via: Literal["cypher", "fulltext", "vector", "expand"]
```

执行顺序：

1. 有实体 → 参数化 Cypher 拉属性（**永不**把用户字符串拼进查询）  
2. `recommend` 且有 city/tags → 图模式匹配  
3. 证据不足或 `open` → 全文索引  
4. 仍不足且配置了 embedding → 向量 TopK  
5. 对已命中节点做一跳 `NEAR` / 同标签（限 5）  

合并去重，截断到 `top_k`（默认 8），再交给生成。

**默认关闭自由 Text2Cypher。** 若打开 `ENABLE_TEXT2CYPHER=true`：只允许 `MATCH/RETURN`，语句需通过白名单校验（禁止 `DELETE/DETACH/CREATE/SET/MERGE/LOAD`）。

---

## 8. 生成与防幻觉

System 约束：

- 只能使用 Evidence 中的事实  
- 每个关键事实带景点名  
- Evidence 没有的属性明确说「知识库暂无」  
- 推荐必须来自检索到的节点，不准虚构地址/票价  
- 简体中文，简洁

无 `LLM_API_KEY`：用模板把属性说成自然语言（保证离线可 demo）。

LangChain 用法（边界）：

- 用：`ChatPromptTemplate`、`PydanticOutputParser`/`with_structured_output`、LCEL（plan | retrieve | generate）、`ChatOpenAI` 兼容网关  
- 不用：无 schema 的 `GraphCypherQAChain` 当主路径、AgentExecutor 套 5 个工具互相喊话

---

## 9. API / CLI / 前端

CLI：`python -m sichuan_qa import|chat|web|eval`

HTTP：

- `GET /` 对话页  
- `POST /api/ask` `{question, session_id}` → `{answer, intent, entities, sources, mode}`  
- `GET /health` Neo4j 连通性  

前端：多轮对话（`session_id` 继承上一轮实体）、来源卡片（属性/标签/命中方式）。

旧规则问答代码已删除，评测只跑 GraphRAG。

---

## 10. 评测

`data/eval/golden.json`（约 25 条，只含图谱中真实存在的景点名）：

| 切片 | 例 | 指标 |
|------|----|------|
| 单跳事实 | 武侯祠的地址 | 属性一致率 |
| 多意图 | 青城山在哪，几点开门 | 属性全中 |
| 推荐 | 成都适合亲子的景点 | Hit@5（黄金名是否在 sources） |
| 拒答 | 某景点明日门票实时余票 | 应拒答，不算编造成功 |
| 无实体开放 | 四川冬天去哪 | 至少 1 条可追溯来源 |

对照：只评 GraphRAG（检索 + 模板；`--llm` 可打开生成）。  
报告：`data/eval/latest.json`（命中率、拒答、平均延迟）。有数字才能写简历。

---

## 11. 工程规范

- 包：`src/sichuan_qa/`，`pyproject.toml` + `requirements.txt`  
- 配置：Pydantic Settings，项目根 `.env`（修复旧 `src/.env` 错误）  
- 驱动：`neo4j` 官方驱动；Cypher 全参数化  
- 日志：`logs/sichuan_qa.log`  
- 旧根目录爬虫脚本可留作数据重建，问答入口不依赖它们  
- 类型注解 + 公共函数 docstring；禁止每行中文注释  

---

## 12. 目标目录

```
SichuanTourismQA-main/
├── docs/OPTIMIZATION.md          # 本文
├── TODO.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── data/eval/golden.json
├── src/sichuan_qa/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── logging_setup.py
│   ├── kg/          schema, connection, importer, enricher
│   ├── nlu/         gazetteer, understand, lexicon
│   ├── rag/         llm, retriever, generator, pipeline
│   └── api/         app.py
├── templates/chat.html
└── tests/           test_enricher, test_nlu, test_retriever_plan
```

数据 CSV、词典仍在原位置，配置指向它们。

---

## 13. 分阶段与工期

| 阶段 | 内容 | 工期 | 依赖 |
|------|------|------|------|
| P0 工程骨架 | 包、配置、依赖、CLI 空壳 | 0.5 天 | 无 |
| P1 图谱重建 | 官方驱动导入、修属性、约束、全文索引 | 1 天 | Neo4j 5+ |
| P2 图增强 | 标签/设施/票价/NEAR | 1 天 | P1 |
| P3 理解+检索 | QueryPlan、混合检索 | 1.5 天 | P2 |
| P4 生成 | LangChain LCEL、模板回退 | 1 天 | P3 |
| P5 API | FastAPI + 对话页 | 1 天 | P4 |
| P6 评测 | 黄金集 + 对照旧系统 | 1～2 天 | P5 |
| P7 可选 | 向量索引、Text2Cypher 白名单、LLM 重标 | 按需 | P6 |

关键路径：P1 → P2 → P3 → P4。没有 P2 就不要对外说 GraphRAG。

---

## 14. 简历表述（P6 评测数字见 `data/eval/latest.json`）

> 将规则模板问答重构为 Neo4j 混合 GraphRAG：景点–城市–标签–设施关系建模，LangChain 做 QueryPlan 路由；事实走参数化 Cypher，推荐走图遍历 + 热度排序，生成强制基于检索证据。黄金集事实/推荐/拒答命中率与延迟见评测报告。

不要写：自研大模型、生产级 RAG 中台、多智能体旅游 OS、相对已删除旧系统的准确率提升。

---

## 15. 风险

| 风险 | 应对 |
|------|------|
| 导入 bug 导致图里没有属性 | P1 用 `MATCH (a:Attraction) RETURN keys(a) LIMIT 5` 自检 |
| Neo4j 未启动 | CLI 明确报错；问答返回 503 |
| 无 LLM Key | 规则理解 + 模板生成，demo 不中断 |
| 标签规则噪声 | 评测抽检；预留 LLM 重标 |
| 词典过杂（灯会、影咖） | 链接仍用词典，推荐用标签+评分降权噪声 |
| langchain 版本漂移 | 只用 langchain-core + langchain-openai 稳定面 |

---

## 16. 验收

1. `python -m sichuan_qa import --clear` 后，景点有 address 等属性，存在 `IN_CITY/HAS_TAG`  
2. 「武侯祠的地址」来自 Cypher，答案带来源  
3. 「成都适合亲子的景点」返回带 `亲子` 标签的节点，不是星火瞎编  
4. 「XX 明天还剩多少票」拒答  
5. 无 Key 时事实题仍能用模板答  
6. `eval` 打出对照表  
