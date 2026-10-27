"""问答主链路：有 Key 走智能体；无 Key 走规则计划 + 图谱检索 + 模板。"""

from __future__ import annotations

from typing import Any

from sichuan_qa.logging_setup import get_logger
from sichuan_qa.nlu.understand import QueryPlan, rule_understand
from sichuan_qa.rag.generator import generate
from sichuan_qa.rag.retriever import EvidenceItem, retrieve

logger = get_logger(__name__)

_REALTIME_INVENTORY = ("余票", "还剩多少", "实时库存", "今天还能买", "明天还剩", "还能买到")
_OUT_OF_REGION = ("故宫", "长城", "外滩", "西湖", "兵马俑", "颐和园")
_INVENTORY_REFUSE = "知识库没有实时余票、当天库存或预订状态，无法回答该问题。"
_FOLLOWUP_HINTS = ("它", "这个", "那个", "这边", "还有呢")
_SESSION_MAX = 256
_SESSIONS: dict[str, dict[str, Any]] = {}


def is_realtime_inventory(question: str) -> bool:
    """余票/库存问法：无智能体时拒答；有智能体时改走购票状态工具。"""
    text = question or ""
    return any(token in text for token in _REALTIME_INVENTORY)


def is_out_of_region(question: str) -> bool:
    return any(token in (question or "") for token in _OUT_OF_REGION)


def is_out_of_scope(question: str) -> bool:
    """外省景点，或（无工具回路时）实时余票。"""
    return is_out_of_region(question) or is_realtime_inventory(question)


def apply_session(plan: QueryPlan, state: dict[str, Any] | None) -> QueryPlan:
    """短问/代词问法继承上一轮实体，避免「它的电话呢」丢上下文。"""
    if not state:
        return plan
    if plan.entities:
        return plan
    prev_entities = list(state.get("entities") or [])
    if not prev_entities:
        return plan
    follow = any(hint in (plan.raw_question or "") for hint in _FOLLOWUP_HINTS)
    attr_only = bool(plan.attributes) and not plan.city and not plan.tags
    if not (follow or attr_only):
        return plan
    plan.entities = prev_entities
    if plan.intent in {"open", "recommend"} and plan.attributes:
        plan.intent = "intro" if set(plan.attributes) <= {"introduction"} else "fact"
    elif plan.intent == "open":
        plan.intent = "intro"
        plan.attributes = plan.attributes or ["introduction"]
    if not plan.city:
        plan.city = state.get("city")
    return plan


def _remember(session_id: str | None, plan: QueryPlan) -> None:
    if not session_id:
        return
    if len(_SESSIONS) >= _SESSION_MAX and session_id not in _SESSIONS:
        _SESSIONS.pop(next(iter(_SESSIONS)))
    prev = _SESSIONS.get(session_id) or {}
    _SESSIONS[session_id] = {
        "entities": plan.entities or prev.get("entities") or [],
        "city": plan.city or prev.get("city"),
        "tags": plan.tags or prev.get("tags") or [],
    }


class QAResult:
    def __init__(
        self,
        question: str,
        answer: str,
        plan: QueryPlan,
        evidence: list[EvidenceItem],
        mode: str,
        tools_used: list[str] | None = None,
        trace: list[dict[str, Any]] | None = None,
    ):
        self.question = question
        self.answer = answer
        self.plan = plan
        self.evidence = evidence
        self.mode = mode
        self.tools_used = tools_used or []
        self.trace = trace or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "intent": self.plan.intent,
            "entities": self.plan.entities,
            "city": self.plan.city,
            "tags": self.plan.tags,
            "attributes": self.plan.attributes,
            "understand_source": self.plan.source,
            "mode": self.mode,
            "tools_used": self.tools_used,
            "trace": self.trace,
            "sources": [
                {
                    "name": item.name,
                    "city": item.city,
                    "tags": item.tags,
                    "facilities": item.facilities,
                    "via": item.via,
                    "properties": {
                        k: v
                        for k, v in item.properties.items()
                        if k not in {"introduction"}
                    },
                    "snippet": item.snippet,
                }
                for item in self.evidence
            ],
        }


def ask(question: str, session_id: str | None = None) -> QAResult:
    from sichuan_qa.rag.llm import llm_available

    question = (question or "").strip()
    # 规则计划只做实体/城市提示和会话继承；有 Key 时由智能体选工具查图谱
    plan = rule_understand(question)
    plan = apply_session(plan, _SESSIONS.get(session_id) if session_id else None)
    if is_out_of_region(question):
        answer = "该问题超出四川旅游知识库范围，无法根据当前图谱回答。"
        _remember(session_id, plan)
        return QAResult(question, answer, plan, [], "refuse")
    realtime = is_realtime_inventory(question)
    if realtime and not llm_available():
        _remember(session_id, plan)
        return QAResult(question, _INVENTORY_REFUSE, plan, [], "refuse")
    if llm_available():
        try:
            from sichuan_qa.rag.agent import run_agent

            answer, evidence, tools_used, trace = run_agent(question, plan)
            plan.source = "agent"
            _remember(session_id, plan)
            return QAResult(question, answer, plan, evidence, "agent", tools_used, trace)
        except Exception as exc:
            logger.warning("智能体回退到流水线: %s", exc)
            if realtime:
                _remember(session_id, plan)
                return QAResult(question, _INVENTORY_REFUSE, plan, [], "refuse")
    evidence = retrieve(plan)
    answer, mode = generate(plan, evidence)
    _remember(session_id, plan)
    return QAResult(question, answer, plan, evidence, mode)
