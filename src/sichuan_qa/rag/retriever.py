"""混合检索：约束 Cypher + 全文 + 一跳扩展。"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from sichuan_qa.config import get_settings
from sichuan_qa.kg.connection import run_query
from sichuan_qa.kg.schema import (
    ATTRACTION_LABEL,
    FACT_ATTRIBUTES,
    REL_HAS_FACILITY,
    REL_HAS_TAG,
    REL_IN_CITY,
    REL_NEAR,
)
from sichuan_qa.logging_setup import get_logger
from sichuan_qa.nlu.lexicon import FAMOUS_ATTRACTIONS
from sichuan_qa.nlu.understand import QueryPlan

logger = get_logger(__name__)

PROP_LABELS = {
    "address": "地址",
    "opening_time": "开放时间",
    "phone": "电话",
    "rating": "评分",
    "popularity": "热度",
    "website": "官网",
    "ticket_info": "门票信息",
    "introduction": "简介",
    "discount_policy": "优待政策",
    "is_free": "是否免费",
    "facilities": "服务设施",
}

_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/|&])')


def sanitize_lucene(query: str) -> str:
    """转义 Lucene 特殊字符，避免全文检索因问号/括号直接失败。"""
    cleaned = _LUCENE_SPECIAL.sub(r"\\\1", query or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "*"


_NOISE_NAME = re.compile(
    r"店\)|店）|\([^)]*店|售票处|观光车|skydive|跳伞|VR|旗舰店|研学|光影大展|演艺秀|别墅|兽舍|产房",
    re.I,
)


def rank_score(item: EvidenceItem) -> float:
    """推荐排序：知名景点 + 热度优先，打压子景点和高分噪声。"""
    name = item.name or ""
    props = item.properties or {}
    try:
        rating = float(props.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        pop = float(props.get("popularity") or 0)
    except (TypeError, ValueError):
        pop = 0.0

    score = rating + pop * 1.6
    if name in FAMOUS_ATTRACTIONS:
        score += 40
    elif any(name.startswith(f"{famous}-") or name.startswith(f"{famous}—") for famous in FAMOUS_ATTRACTIONS):
        score -= 18
    elif any(famous in name for famous in FAMOUS_ATTRACTIONS):
        score += 8
    if _NOISE_NAME.search(name):
        score -= 25
    if "-" in name or "—" in name:
        score -= 10
    extra = len(name) - 16
    if extra > 0:
        score -= min(extra, 12)
    return score


class EvidenceItem(BaseModel):
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    city: str | None = None
    tags: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    neighbors: list[str] = Field(default_factory=list)
    snippet: str | None = None
    via: Literal["cypher", "fulltext", "vector", "expand"] = "cypher"


def _clean_props(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    skip = {"embedding", "facilities_text"}
    return {k: v for k, v in raw.items() if v is not None and k not in skip}


def fetch_by_names(names: list[str]) -> list[EvidenceItem]:
    if not names:
        return []
    rows = run_query(
        f"""
        MATCH (a:{ATTRACTION_LABEL})
        WHERE a.name IN $names
        OPTIONAL MATCH (a)-[:{REL_IN_CITY}]->(c)
        OPTIONAL MATCH (a)-[:{REL_HAS_TAG}]->(t)
        OPTIONAL MATCH (a)-[:{REL_HAS_FACILITY}]->(f)
        OPTIONAL MATCH (a)-[:{REL_NEAR}]->(n)
        RETURN a AS node, c.name AS city, collect(DISTINCT t.name) AS tags,
               collect(DISTINCT f.name) AS facilities,
               collect(DISTINCT n.name) AS neighbors
        """,
        {"names": names},
    )
    items: list[EvidenceItem] = []
    for row in rows:
        node = row.get("node") or {}
        name = node.get("name")
        if not name:
            continue
        items.append(
            EvidenceItem(
                name=name,
                properties=_clean_props(dict(node)),
                city=row.get("city"),
                tags=[t for t in (row.get("tags") or []) if t],
                facilities=[f for f in (row.get("facilities") or []) if f],
                neighbors=[n for n in (row.get("neighbors") or []) if n][:5],
                snippet=(node.get("introduction") or "")[:180] or None,
                via="cypher",
            )
        )
    return items


def recommend(city: str | None, tags: list[str], limit: int) -> list[EvidenceItem]:
    clauses = [f"MATCH (a:{ATTRACTION_LABEL})"]
    where: list[str] = []
    params: dict[str, Any] = {"limit": max(limit * 5, 40)}
    if city:
        clauses.append(f"MATCH (a)-[:{REL_IN_CITY}]->(c)")
        where.append("c.name = $city")
        params["city"] = city
    if tags:
        clauses.append(f"MATCH (a)-[:{REL_HAS_TAG}]->(t)")
        where.append("t.name IN $tags")
        params["tags"] = tags
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    cypher = (
        "\n".join(clauses)
        + where_sql
        + f"""
        OPTIONAL MATCH (a)-[:{REL_IN_CITY}]->(city)
        OPTIONAL MATCH (a)-[:{REL_HAS_TAG}]->(tag)
        OPTIONAL MATCH (a)-[:{REL_NEAR}]->(n)
        RETURN DISTINCT a AS node, city.name AS city, collect(DISTINCT tag.name) AS tags,
               collect(DISTINCT n.name) AS neighbors
        ORDER BY coalesce(a.popularity, 0) DESC, coalesce(a.rating, 0) DESC
        LIMIT $limit
        """
    )
    rows = run_query(cypher, params)
    results = []
    for row in rows:
        node = row.get("node") or {}
        name = node.get("name")
        if not name:
            continue
        results.append(
            EvidenceItem(
                name=name,
                properties=_clean_props(dict(node)),
                city=row.get("city"),
                tags=[t for t in (row.get("tags") or []) if t],
                neighbors=[n for n in (row.get("neighbors") or []) if n][:5],
                snippet=(node.get("introduction") or "")[:180] or None,
                via="cypher",
            )
        )
    return results


def fulltext_search(question: str, limit: int) -> list[EvidenceItem]:
    try:
        rows = run_query(
            f"""
            CALL db.index.fulltext.queryNodes('attraction_fulltext', $q) YIELD node, score
            OPTIONAL MATCH (node)-[:{REL_IN_CITY}]->(c)
            OPTIONAL MATCH (node)-[:{REL_HAS_TAG}]->(t)
            RETURN node, c.name AS city, collect(DISTINCT t.name) AS tags, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            {"q": sanitize_lucene(question), "limit": limit},
        )
    except Exception as exc:
        logger.warning("全文检索不可用: %s", exc)
        return []
    items = []
    for row in rows:
        node = row.get("node") or {}
        name = node.get("name")
        if not name:
            continue
        items.append(
            EvidenceItem(
                name=name,
                properties=_clean_props(dict(node)),
                city=row.get("city"),
                tags=[t for t in (row.get("tags") or []) if t],
                snippet=(node.get("introduction") or "")[:180] or None,
                via="fulltext",
            )
        )
    return items


def merge_evidence(batches: list[list[EvidenceItem]], limit: int) -> list[EvidenceItem]:
    merged: dict[str, EvidenceItem] = {}
    for batch in batches:
        for item in batch:
            if item.name not in merged:
                merged[item.name] = item
    return list(merged.values())[:limit]


def _is_nearby_query(plan: QueryPlan) -> bool:
    question = plan.raw_question or ""
    return bool(plan.entities) and any(
        word in question for word in ("附近", "周边", "还能去", "还可以去", "旁边")
    )


def retrieve(plan: QueryPlan) -> list[EvidenceItem]:
    settings = get_settings()
    k = settings.retrieve_top_k
    batches: list[list[EvidenceItem]] = []
    nearby = plan.intent == "recommend" and _is_nearby_query(plan)

    if plan.entities:
        batches.append(fetch_by_names(plan.entities))

    if not nearby and (plan.intent == "recommend" or (plan.city and plan.tags)):
        batches.append(recommend(plan.city, plan.tags, k))

    if plan.intent == "open" or not any(batches):
        batches.append(fulltext_search(plan.raw_question, k))

    pool_limit = max(k * 5, 40) if plan.intent == "recommend" else k
    evidence = merge_evidence(batches, pool_limit)

    if plan.intent == "recommend":
        evidence = sorted(evidence, key=rank_score, reverse=True)
        positive = [item for item in evidence if rank_score(item) > 0]
        evidence = (positive or evidence)[:k]
        if plan.entities:
            extra_names: list[str] = []
            for item in evidence[:3]:
                extra_names.extend(item.neighbors)
            extra_names = [n for n in extra_names if n not in {e.name for e in evidence}]
            if extra_names:
                expanded = fetch_by_names(extra_names[:k])
                for item in expanded:
                    item.via = "expand"
                evidence = sorted(merge_evidence([evidence, expanded], pool_limit), key=rank_score, reverse=True)
                positive = [item for item in evidence if rank_score(item) > 0]
                evidence = (positive or evidence)[:k]

    if plan.attributes:
        wanted = [a for a in plan.attributes if a in FACT_ATTRIBUTES or a in {"ticket_info", "facilities"}]
        if wanted:
            keep = set(wanted) | {"name", "is_free"}
            for item in evidence:
                filtered = {
                    key: value
                    for key, value in item.properties.items()
                    if key in keep
                }
                if filtered:
                    item.properties = filtered
    return evidence


def evidence_to_context(items: list[EvidenceItem]) -> str:
    if not items:
        return "（知识库未检索到相关景点）"
    blocks = []
    for item in items:
        lines = [f"景点: {item.name}"]
        if item.city:
            lines.append(f"城市: {item.city}")
        if item.tags:
            lines.append("标签: " + "、".join(item.tags))
        if item.facilities:
            lines.append("设施: " + "、".join(item.facilities[:12]))
        for key, value in item.properties.items():
            if key == "name":
                continue
            label = PROP_LABELS.get(key, key)
            text = str(value)
            if key == "introduction" and len(text) > 400:
                text = text[:400] + "…"
            lines.append(f"{label}: {text}")
        if item.neighbors:
            lines.append("相关推荐: " + "、".join(item.neighbors[:5]))
        lines.append(f"来源通道: {item.via}")
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)
