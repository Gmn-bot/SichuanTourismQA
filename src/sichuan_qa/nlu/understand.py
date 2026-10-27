"""查询理解：规则 QueryPlan，供会话继承和智能体提示；选工具由 ReAct 完成。"""

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
