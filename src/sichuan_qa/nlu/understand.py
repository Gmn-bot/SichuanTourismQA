"""查询理解：LLM 结构化 QueryPlan，失败则规则回退。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sichuan_qa.nlu.gazetteer import get_gazetteer
from sichuan_qa.nlu.lexicon import (
    ATTR_FROM_INTENT,
    CITY_NAMES,
    COMPARE_KEYWORDS,
    INTENT_KEYWORDS,
    RECOMMEND_KEYWORDS,
    TAG_KEYWORDS,
)

IntentType = Literal["fact", "intro", "recommend", "compare", "open"]


class QueryPlan(BaseModel):
    intent: IntentType = "open"
    entities: list[str] = Field(default_factory=list)
    city: str | None = None
    tags: list[str] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)
    raw_question: str = ""
    source: str = "rules"


def _contains_any(question: str, words: list[str]) -> bool:
    return any(word in question for word in words)


def rule_understand(question: str) -> QueryPlan:
    entities = get_gazetteer().extract(question)
    attributes: list[str] = []
    for intent_key, words in INTENT_KEYWORDS.items():
        if _contains_any(question, words):
            attributes.append(ATTR_FROM_INTENT[intent_key])

    city = None
    # 长名优先；若城市名只出现在景点名内部（乐山⊂乐山大佛）则丢掉
    leftover = question
    for entity in entities:
        leftover = leftover.replace(entity, "")
    for name in sorted(CITY_NAMES, key=len, reverse=True):
        if name in leftover:
            city = name
            break

    tags = [tag for tag, words in TAG_KEYWORDS.items() if _contains_any(question, words)]

    if len(entities) >= 2 and _contains_any(question, COMPARE_KEYWORDS):
        intent: IntentType = "compare"
    elif _contains_any(question, RECOMMEND_KEYWORDS) or (city and not entities):
        intent = "recommend"
    elif entities and attributes and set(attributes) <= {"introduction"}:
        intent = "intro"
    elif entities and attributes:
        intent = "fact"
    elif entities and not attributes:
        intent = "intro"
        attributes = ["introduction"]
    else:
        intent = "open"

    if intent == "recommend" and not tags and "免费" in question:
        tags.append("免费")

    return QueryPlan(
        intent=intent,
        entities=entities,
        city=city,
        tags=tags,
        attributes=attributes or (["introduction"] if intent == "intro" else []),
        raw_question=question,
        source="rules",
    )


def llm_understand(question: str, fallback: QueryPlan) -> QueryPlan:
    from sichuan_qa.rag.llm import get_chat_model

    model = get_chat_model()
    if model is None:
        return fallback
    try:
        structured = model.with_structured_output(QueryPlan)
        prompt = (
            "你是四川旅游问答的查询规划器。根据用户问题产出 QueryPlan。\n"
            "intent 只能是 fact/intro/recommend/compare/open。\n"
            "entities 必须来自候选列表，不许发明景点名。\n"
            "attributes 只能是: address, opening_time, phone, rating, popularity, "
            "website, ticket_info, introduction, discount_policy, facilities。\n"
            f"候选实体: {fallback.entities or '无'}\n"
            f"规则预分析结果: {fallback.model_dump_json(ensure_ascii=False)}\n"
            f"用户问题: {question}"
        )
        plan = structured.invoke(prompt)
        if not isinstance(plan, QueryPlan):
            return fallback
        allowed = set(fallback.entities)
        plan.entities = [e for e in plan.entities if e in allowed] or fallback.entities
        plan.raw_question = question
        plan.source = "llm"
        if not plan.attributes and plan.intent in {"fact", "intro"}:
            plan.attributes = fallback.attributes
        return plan
    except Exception:
        return fallback


def understand(question: str) -> QueryPlan:
    from sichuan_qa.rag.llm import llm_available

    fallback = rule_understand(question)
    if llm_available():
        return llm_understand(question, fallback)
    return fallback
