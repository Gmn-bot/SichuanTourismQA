# GraphRAG TODO

对应设计：[docs/OPTIMIZATION.md](docs/OPTIMIZATION.md)

仓库只保留新系统，不再对照旧规则问答。

## 已完成

- [x] 工程骨架（包、配置、CLI、黄金集）
- [x] Neo4j 官方驱动导入（英文标签、约束、全文、自检）
- [x] 图增强（标签只看景点名、设施、票价/免费、NEAR）
- [x] QueryPlan + 混合检索 + 证据生成 + 拒答
- [x] 推荐排序（知名景点 + 热度，打压 5.0 噪声/子景点）
- [x] FastAPI `/api/ask` `/health` + 来源卡片 + 会话继承
- [x] 黄金集评测（`python run.py eval`，报告 `data/eval/latest.json`）
- [x] 去掉旧 Flask / py2neo / 星火基线代码
- [x] 文旅智能体（tool-calling 调 GraphRAG：lookup / recommend / nearby / compare / search）
- [x] 联网工具：票价公开检索 + Open-Meteo 天气 + 余票/购票渠道（无库存接口则如实说明）
- [x] ReAct 循环（原生 tool-calling：思考 → 行动 → 观察，轨迹写入 API/页面）

## 可选后续（主路径不需要）

- [ ] 向量索引
- [ ] 白名单 Text2Cypher
- [ ] LLM 离线重标标签
