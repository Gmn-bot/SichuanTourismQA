"""文旅咨询智能体：用工具调用现有 GraphRAG 检索，禁止凭记忆编造。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sichuan_qa.logging_setup import get_logger
from sichuan_qa.nlu.gazetteer import get_gazetteer
from sichuan_qa.nlu.lexicon import CITY_NAMES
from sichuan_qa.nlu.understand import QueryPlan
from sichuan_qa.rag.generator import template_answer
from sichuan_qa.rag.retriever import EvidenceItem, evidence_to_context, fetch_by_names, retrieve
from sichuan_qa.rag.web_tools import fetch_weather, search_web_snippets

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 6
OBS_CLIP = 280
_ATTR_ALIASES = {
    "地址": "address",
    "开放时间": "opening_time",
    "开门时间": "opening_time",
    "开门": "opening_time",
    "电话": "phone",
    "评分": "rating",
    "热度": "popularity",
    "官网": "website",
    "门票": "ticket_info",
    "票价": "ticket_info",
    "简介": "introduction",
    "介绍": "introduction",
    "优待": "discount_policy",
    "优待政策": "discount_policy",
    "设施": "facilities",
}
_ATTRS = (
    "address",
    "opening_time",
    "phone",
    "rating",
    "popularity",
    "website",
    "ticket_info",
    "introduction",
    "discount_policy",
    "facilities",
)

_scratch: ContextVar[dict[str, Any]] = ContextVar("agent_scratch")

SYSTEM_PROMPT = """你是四川省文化和旅游系统的智能咨询助手，按 ReAct 循环工作：
思考（还缺什么证据、该用哪一个工具）→ 调用工具 → 阅读观察 → 不够就再思考再调用 → 证据足够再给出最终答案。
必须先调用工具再最终作答，禁止用自身记忆编造地址、电话、票价、余票、开放时间、评分、天气。
调用工具时用一两句中文写出思考（例如「用户问开放时间，应查图谱事实」）。

工具怎么选：
- 景点事实（地址/电话/开放时间/设施）：lookup_fact_tool
- 门票多少钱、官网价、门市价：lookup_ticket_price_tool（图谱 + 公开网页报价）
- 余票、当天库存、还能买到吗、要不要预约：lookup_booking_status_tool（查官网/电话/预约入口）
- 天气、气温、会不会下雨：get_weather_tool
- 城市/标签推荐：recommend_attractions_tool
- 附近还能去哪：nearby_attractions_tool
- 对比景点：compare_attractions_tool
- 没有明确景点名的开放问法：search_open_tool

一个问题含多个意图时，可同一轮并行调用多个工具，或下一轮补调；观察不够不要提前最终作答。
余票 ≠ 票价。问价格用 lookup_ticket_price_tool；问余票/能否买到必须调用 lookup_booking_status_tool，不要直接拒答，也不要编造剩余张数。
问天气必须调用 get_weather_tool，不要猜。
联网结果只是公开网页摘要，必须声明「以景区官网为准」。
最终答案用简洁中文，关键事实带上景点名。
"""


def _canon_names(names: list[str] | None) -> list[str]:
    gazetteer = get_gazetteer()
    out: list[str] = []
    seen: set[str] = set()
    for raw in names or []:
        text = (raw or "").strip()
        if not text:
            continue
        resolved = gazetteer.extract(text) or [text]
        for name in resolved:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _collect(items: list[EvidenceItem]) -> str:
    bucket = _scratch.get()
    merged: dict[str, EvidenceItem] = {item.name: item for item in bucket["evidence"]}
    for item in items:
        merged.setdefault(item.name, item)
    bucket["evidence"] = list(merged.values())
    if not items:
        return "知识库未检索到相关景点。"
    return evidence_to_context(items)


def _norm_attrs(attributes: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in attributes or []:
        key = _ATTR_ALIASES.get((raw or "").strip(), (raw or "").strip())
        if key in _ATTRS and key not in out:
            out.append(key)
    return out


def lookup_fact(names: list[str], attributes: list[str] | None = None) -> str:
    """查询景点事实：地址、开放时间、电话、门票政策、设施、简介等。"""
    entities = _canon_names(names)
    attrs = _norm_attrs(attributes)
    plan = QueryPlan(
        intent="fact" if attrs else "intro",
        entities=entities,
        attributes=attrs or ["introduction"],
        raw_question=" ".join(entities),
        source="agent",
    )
    return _collect(retrieve(plan))


def recommend_attractions(city: str | None = None, tags: list[str] | None = None) -> str:
    """按城市和标签推荐四川景点，例如成都+亲子、成都+免费。"""
    plan = QueryPlan(
        intent="recommend",
        city=(city or "").strip() or None,
        tags=[t for t in (tags or []) if t],
        raw_question=f"{city or ''} {' '.join(tags or [])} 推荐",
        source="agent",
    )
    return _collect(retrieve(plan))


def nearby_attractions(name: str) -> str:
    """查询某景点附近还能去哪些地方（图谱 NEAR 关系）。"""
    entities = _canon_names([name])
    if not entities:
        return "请提供图谱中的景点名称。"
    plan = QueryPlan(
        intent="recommend",
        entities=entities,
        raw_question=f"去了{entities[0]}还可以去哪些附近景点？",
        source="agent",
    )
    return _collect(retrieve(plan))


def compare_attractions(names: list[str]) -> str:
    """对比两个或多个景点的评分、城市、标签。"""
    entities = _canon_names(names)
    plan = QueryPlan(
        intent="compare",
        entities=entities,
        attributes=["rating", "address", "opening_time"],
        raw_question="对比",
        source="agent",
    )
    return _collect(retrieve(plan))


def search_open(query: str) -> str:
    """开放问法：没有明确景点名时，用全文检索四川景点。"""
    plan = QueryPlan(intent="open", raw_question=query or "", source="agent")
    return _collect(retrieve(plan))


def _place_city(place: str) -> str:
    text = (place or "").strip()
    entities = _canon_names([text]) if text else []
    if entities:
        items = fetch_by_names(entities[:1])
        if items and items[0].city:
            return items[0].city
    leftover = text
    for name in entities:
        leftover = leftover.replace(name, "")
    for city in sorted(CITY_NAMES, key=len, reverse=True):
        if city in leftover or city == text:
            return city
    return leftover or text or "成都"


def get_weather(place: str) -> str:
    """查询某城市或景点所在地的实时天气与近两日预报。"""
    city = _place_city(place)
    try:
        return fetch_weather(city)
    except Exception as exc:
        logger.warning("天气查询失败: %s", exc)
        return f"天气接口暂时不可用：{exc}"


def lookup_ticket_price(name: str) -> str:
    """查询门票价格：先读知识图谱，再联网检索公开网页报价（不是余票）。"""
    entities = _canon_names([name]) or [name]
    plan = QueryPlan(
        intent="fact",
        entities=entities,
        attributes=["ticket_info", "discount_policy", "is_free", "website"],
        raw_question=f"{entities[0]}门票多少钱",
        source="agent",
    )
    kg_text = _collect(retrieve(plan))
    query = f"{entities[0]} 门票 价格 官网"
    try:
        web_text = search_web_snippets(query)
    except Exception as exc:
        logger.warning("票价联网检索失败: %s", exc)
        web_text = f"联网检索失败：{exc}"
    return (
        kg_text
        + "\n\n"
        + web_text
        + "\n说明：以上不是实时余票，不能用于下单；请以景区官网或窗口当日价格为准。"
    )


def lookup_booking_status(name: str) -> str:
    """查询余票/能否买到：给出官网、电话、预约入口；没有实时库存接口则如实说明。"""
    entities = _canon_names([name]) or [name]
    plan = QueryPlan(
        intent="fact",
        entities=entities,
        attributes=["website", "phone", "ticket_info", "opening_time"],
        raw_question=f"{entities[0]}还能买到票吗",
        source="agent",
    )
    kg_text = _collect(retrieve(plan))
    query = f"{entities[0]} 门票预约 购票 官网"
    try:
        web_text = search_web_snippets(query)
    except Exception as exc:
        logger.warning("购票渠道检索失败: %s", exc)
        web_text = f"联网检索失败：{exc}"
    return (
        "【余票查询】没有景区订票库存接口，不能返回实时剩余张数或锁定名额。"
        "请到景区官网、官方预约小程序或窗口查看当日可售情况。\n\n"
        + kg_text
        + "\n\n"
        + web_text
        + "\n说明：禁止把网页摘要当成余票数字。"
    )


def _langchain_tools():
    from langchain_core.tools import tool

    @tool
    def lookup_fact_tool(names: list[str], attributes: list[str] | None = None) -> str:
        """查询四川景点的地址、开放时间、电话、设施、简介。attributes 用 address/opening_time/phone 等字段名，也接受「开放时间」中文。票价请改用 lookup_ticket_price_tool。"""
        return lookup_fact(names, attributes)

    @tool
    def recommend_attractions_tool(city: str | None = None, tags: list[str] | None = None) -> str:
        """按城市和标签推荐景点。tags 如 亲子、免费、自然、人文、游乐。"""
        return recommend_attractions(city, tags)

    @tool
    def nearby_attractions_tool(name: str) -> str:
        """查询某景点附近还能去哪些地方。"""
        return nearby_attractions(name)

    @tool
    def compare_attractions_tool(names: list[str]) -> str:
        """对比两个或多个景点。"""
        return compare_attractions(names)

    @tool
    def search_open_tool(query: str) -> str:
        """没有明确景点名的开放问法，全文检索四川景点。"""
        return search_open(query)

    @tool
    def get_weather_tool(place: str) -> str:
        """查询城市或景点所在地天气。place 可以是成都、乐山，或景点名。"""
        return get_weather(place)

    @tool
    def lookup_ticket_price_tool(name: str) -> str:
        """查询门票价格：知识图谱 + 联网公开网页。不是余票/能否买到。"""
        return lookup_ticket_price(name)

    @tool
    def lookup_booking_status_tool(name: str) -> str:
        """查询余票、当天库存、还能买到吗、要不要预约。给出官网/电话/预约入口，不编造剩余张数。"""
        return lookup_booking_status(name)

    return [
        lookup_fact_tool,
        recommend_attractions_tool,
        nearby_attractions_tool,
        compare_attractions_tool,
        search_open_tool,
        get_weather_tool,
        lookup_ticket_price_tool,
        lookup_booking_status_tool,
    ]


def as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
        return "".join(parts).strip()
    return str(content).strip()


def clip_text(text: str, limit: int = OBS_CLIP) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _public_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if isinstance(value, str) and len(value) > 80:
            out[key] = value[:80] + "…"
        else:
            out[key] = value
    return out


def _tool_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_args(call: Any) -> dict[str, Any]:
    if isinstance(call, dict):
        args = call.get("args") or call.get("arguments") or {}
    else:
        args = getattr(call, "args", {}) or {}
    if isinstance(args, str):
        import json

        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return args if isinstance(args, dict) else {}


def _tool_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or call.get("tool_call_id") or "")
    return str(getattr(call, "id", "") or "")


def run_agent(question: str, plan: QueryPlan) -> tuple[str, list[EvidenceItem], list[str], list[dict[str, Any]]]:
    """ReAct：思考 → 原生 tool-calling → 观察，可多轮。返回 (答案, 证据, 工具名, 轨迹)。"""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    from sichuan_qa.rag.llm import get_chat_model

    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM 不可用")

    tools = _langchain_tools()
    tool_map = {t.name: t for t in tools}
    bound = model.bind_tools(tools)
    token = _scratch.set({"evidence": [], "tools": [], "trace": []})
    try:
        hint = ""
        if plan.entities or plan.city or plan.tags:
            hint = (
                f"\n规则预分析：实体={plan.entities or '无'}，"
                f"城市={plan.city or '无'}，标签={plan.tags or '无'}。"
                "实体名若在候选中，优先用这些正式名调用工具。"
            )
        messages: list[Any] = [
            SystemMessage(content=SYSTEM_PROMPT + hint),
            HumanMessage(content=question),
        ]
        final_text = ""
        for _ in range(MAX_TOOL_ROUNDS):
            ai = bound.invoke(messages)
            messages.append(ai)
            calls = getattr(ai, "tool_calls", None) or []
            thought = as_text(getattr(ai, "content", None))
            if not calls:
                final_text = thought
                break
            actions: list[dict[str, Any]] = []
            for call in calls:
                name = _tool_name(call)
                args = _tool_args(call)
                _scratch.get()["tools"].append(name)
                selected = tool_map.get(name)
                if selected is None:
                    result = f"未知工具: {name}"
                else:
                    try:
                        result = selected.invoke(args)
                    except Exception as exc:
                        logger.warning("工具 %s 失败: %s", name, exc)
                        result = f"工具执行失败: {exc}"
                actions.append(
                    {
                        "tool": name,
                        "args": _public_args(args),
                        "observation": clip_text(str(result)),
                    }
                )
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=_tool_id(call) or name)
                )
            _scratch.get()["trace"].append({"thought": thought or None, "actions": actions})
        evidence = list(_scratch.get()["evidence"])
        tools_used = list(_scratch.get()["tools"])
        trace = list(_scratch.get()["trace"])
        if not tools_used:
            raise RuntimeError("智能体未调用任何工具")
        if not final_text:
            final_text = template_answer(plan, evidence)
        return final_text, evidence, tools_used, trace
    finally:
        _scratch.reset(token)
