"""基于证据的答案生成：LangChain LCEL，无 LLM 时模板回退。"""

from __future__ import annotations

from sichuan_qa.nlu.understand import QueryPlan
from sichuan_qa.rag.llm import get_chat_model, llm_available
from sichuan_qa.rag.retriever import PROP_LABELS, EvidenceItem, evidence_to_context

SYSTEM_PROMPT = """你是四川旅游知识图谱助手。必须遵守：
1. 只能使用「检索证据」里的事实，禁止编造地址、电话、票价、开放时间。
2. 证据没有的字段要明确说「知识库暂无」。
3. 推荐只能来自证据中出现的景点名称。
4. 用简洁中文回答，关键事实带上景点名。
5. 不要输出思维过程。"""


def template_answer(plan: QueryPlan, items: list[EvidenceItem]) -> str:
    if not items:
        if plan.entities:
            return f"抱歉，知识库中没有找到与「{'、'.join(plan.entities)}」匹配的可引用信息。"
        return "抱歉，知识库中没有检索到能支撑该回答的景点证据。请换个景点名或更具体的问法。"

    if plan.intent == "compare" and len(items) >= 2:
        lines = ["根据知识图谱对比如下："]
        for item in items:
            rating = item.properties.get("rating")
            city = item.city or "未知城市"
            score = f"评分 {rating}" if rating is not None else "评分：知识库暂无"
            lines.append(f"- {item.name}（{city}，{score}）")
        return "\n".join(lines)

    parts: list[str] = []
    attrs = plan.attributes or []
    for item in items:
        name = item.name
        if plan.intent == "recommend":
            bits = [b for b in [item.city, "、".join(item.tags) if item.tags else ""] if b]
            score = item.properties.get("rating")
            score_text = f"，评分 {score}" if score is not None else ""
            extra = " · ".join(bits) if bits else "综合"
            parts.append(f"{name}（{extra}{score_text}）")
            continue

        sentences = []
        keys = attrs or list(item.properties.keys())
        if "facilities" in keys:
            fac = "、".join(item.facilities) if item.facilities else None
            if fac:
                sentences.append(f"{name}的服务设施包括：{fac}")
            elif "facilities" in attrs:
                sentences.append(f"{name}的服务设施：知识库暂无。")
        for key in keys:
            if key in {"name", "facilities"}:
                continue
            value = item.properties.get(key)
            if value is None or value == "":
                if key in attrs:
                    sentences.append(f"{name}的{PROP_LABELS.get(key, key)}：知识库暂无。")
                continue
            label = PROP_LABELS.get(key, key)
            sentences.append(f"{name}的{label}是：{value}")
        if not sentences and item.snippet:
            sentences.append(f"{name}的简介：{item.snippet}")
        if not sentences:
            sentences.append(f"已找到景点「{name}」，但请求的字段在库中为空。")
        parts.append("。".join(sentences) + ("。" if sentences else ""))

    if plan.intent == "recommend":
        header = "根据知识图谱，为你找到以下景点："
        return header + "\n- " + "\n- ".join(parts)
    return "\n".join(parts)


def llm_answer(question: str, items: list[EvidenceItem]) -> str | None:
    model = get_chat_model()
    if model is None:
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                (
                    "human",
                    "用户问题：{question}\n\n检索证据：\n{context}\n\n请给出回答。",
                ),
            ]
        )
        chain = prompt | model | StrOutputParser()
        return chain.invoke({"question": question, "context": evidence_to_context(items)})
    except Exception:
        return None


def generate(plan: QueryPlan, items: list[EvidenceItem]) -> tuple[str, str]:
    """返回 (answer, mode)。mode: llm | template | refuse"""
    if not items:
        return template_answer(plan, items), "refuse"
    if llm_available():
        text = llm_answer(plan.raw_question, items)
        if text:
            return text.strip(), "llm"
    return template_answer(plan, items), "template"
