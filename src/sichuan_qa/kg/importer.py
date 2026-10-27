"""将三元组 CSV 导入 Neo4j（英文标签 + 增强关系）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from sichuan_qa.config import get_settings
from sichuan_qa.kg.connection import get_driver, session_scope, verify_connectivity
from sichuan_qa.kg.enricher import build_near_pairs, enrich_attraction
from sichuan_qa.kg.schema import (
    ATTRACTION_LABEL,
    CITY_LABEL,
    CITY_PREDICATE,
    CONSTRAINT_STATEMENTS,
    FACILITY_LABEL,
    FLOAT_PROPS,
    FULLTEXT_INDEX,
    PREDICATE_TO_PROP,
    REL_HAS_FACILITY,
    REL_HAS_TAG,
    REL_IN_CITY,
    REL_NEAR,
    TAG_LABEL,
)
from sichuan_qa.logging_setup import get_logger

logger = get_logger(__name__)

BATCH = 200


def _to_value(prop: str, raw: Any) -> Any:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return None
    if prop in FLOAT_PROPS:
        try:
            return float(text)
        except ValueError:
            return None
    return text


def load_attractions(csv_path: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    required = {"subject", "predicate", "object"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"三元组缺少列: {missing}")

    props: dict[str, dict[str, Any]] = defaultdict(dict)
    city_of: dict[str, str] = {}

    for row in df.itertuples(index=False):
        subject = str(getattr(row, "subject", "") or "").strip()
        predicate = str(getattr(row, "predicate", "") or "").strip()
        obj = getattr(row, "object", None)
        if not subject or not predicate:
            continue
        if predicate == CITY_PREDICATE:
            city = _to_value("city", obj)
            if city:
                city_of[subject] = city
            continue
        prop = PREDICATE_TO_PROP.get(predicate)
        if not prop:
            continue
        value = _to_value(prop, obj)
        if value is not None:
            props[subject][prop] = value

    attractions: list[dict[str, Any]] = []
    for name, data in props.items():
        record = {"name": name, **data}
        attractions.append(enrich_attraction(record))
    return attractions, city_of


def _ensure_schema(session) -> None:
    for stmt in CONSTRAINT_STATEMENTS:
        session.run(stmt)
    session.run(FULLTEXT_INDEX)


def _reset_derived(session) -> None:
    session.run(f"MATCH ()-[r:{REL_HAS_TAG}|{REL_HAS_FACILITY}|{REL_NEAR}]->() DELETE r")
    session.run(f"MATCH (t:{TAG_LABEL}) WHERE NOT ()-[:{REL_HAS_TAG}]->(t) DELETE t")
    session.run(f"MATCH (f:{FACILITY_LABEL}) WHERE NOT ()-[:{REL_HAS_FACILITY}]->(f) DELETE f")


def _clear_graph(session) -> None:
    session.run("MATCH (n) DETACH DELETE n")
    logger.warning("已清空 Neo4j 全部节点和关系")


def _write_in_batches(session, cypher: str, rows: list[dict[str, Any]]) -> None:
    for i in range(0, len(rows), BATCH):
        session.run(cypher, {"rows": rows[i : i + BATCH]})


def import_knowledge_graph(csv_path: str | None = None, clear: bool = False) -> dict[str, int]:
    settings = get_settings()
    path = csv_path or settings.triplet_csv
    verify_connectivity()
    attractions, city_of = load_attractions(path)
    near_pairs = build_near_pairs(attractions, city_of, limit=settings.near_limit)

    attraction_rows = []
    tag_rows = []
    facility_rows = []
    city_rows = [{"name": city} for city in sorted(set(city_of.values()))]
    in_city_rows = [{"name": n, "city": c} for n, c in city_of.items()]

    for item in attractions:
        attraction_rows.append(
            {
                "name": item["name"],
                "address": item.get("address"),
                "rating": item.get("rating"),
                "popularity": item.get("popularity"),
                "opening_time": item.get("opening_time"),
                "phone": item.get("phone"),
                "introduction": item.get("introduction"),
                "discount_policy": item.get("discount_policy"),
                "website": item.get("website"),
                "ticket_info": item.get("ticket_info"),
                "is_free": bool(item.get("is_free")),
                "facilities_text": item.get("facilities_text"),
            }
        )
        for tag in item.get("tags") or []:
            tag_rows.append({"name": item["name"], "tag": tag})
        for fac in item.get("facilities") or []:
            facility_rows.append({"name": item["name"], "facility": fac})

    driver = get_driver()
    with driver.session() as session:
        if clear:
            _clear_graph(session)
        _ensure_schema(session)
        if not clear:
            _reset_derived(session)

        _write_in_batches(
            session,
            f"""
            UNWIND $rows AS row
            MERGE (a:{ATTRACTION_LABEL} {{name: row.name}})
            SET a.address = row.address,
                a.rating = row.rating,
                a.popularity = row.popularity,
                a.opening_time = row.opening_time,
                a.phone = row.phone,
                a.introduction = row.introduction,
                a.discount_policy = row.discount_policy,
                a.website = row.website,
                a.ticket_info = row.ticket_info,
                a.is_free = row.is_free,
                a.facilities_text = row.facilities_text
            """,
            attraction_rows,
        )
        if city_rows:
            _write_in_batches(
                session,
                f"UNWIND $rows AS row MERGE (c:{CITY_LABEL} {{name: row.name}})",
                city_rows,
            )
        if in_city_rows:
            _write_in_batches(
                session,
                f"""
                UNWIND $rows AS row
                MATCH (a:{ATTRACTION_LABEL} {{name: row.name}})
                MERGE (c:{CITY_LABEL} {{name: row.city}})
                MERGE (a)-[:{REL_IN_CITY}]->(c)
                """,
                in_city_rows,
            )
        if tag_rows:
            _write_in_batches(
                session,
                f"""
                UNWIND $rows AS row
                MATCH (a:{ATTRACTION_LABEL} {{name: row.name}})
                MERGE (t:{TAG_LABEL} {{name: row.tag}})
                MERGE (a)-[:{REL_HAS_TAG}]->(t)
                """,
                tag_rows,
            )
        if facility_rows:
            _write_in_batches(
                session,
                f"""
                UNWIND $rows AS row
                MATCH (a:{ATTRACTION_LABEL} {{name: row.name}})
                MERGE (f:{FACILITY_LABEL} {{name: row.facility}})
                MERGE (a)-[:{REL_HAS_FACILITY}]->(f)
                """,
                facility_rows,
            )
        if near_pairs:
            near_rows = [{"a": a, "b": b, "reason": r} for a, b, r in near_pairs]
            _write_in_batches(
                session,
                f"""
                UNWIND $rows AS row
                MATCH (a:{ATTRACTION_LABEL} {{name: row.a}})
                MATCH (b:{ATTRACTION_LABEL} {{name: row.b}})
                MERGE (a)-[rel:{REL_NEAR}]->(b)
                SET rel.reason = row.reason
                """,
                near_rows,
            )

    stats = {
        "attractions": len(attraction_rows),
        "cities": len(city_rows),
        "tag_links": len(tag_rows),
        "facility_links": len(facility_rows),
        "near_links": len(near_pairs),
    }
    logger.info("导入完成: %s", stats)
    _self_check()
    return stats


def _self_check() -> None:
    with session_scope() as session:
        rec = session.run(
            f"MATCH (a:{ATTRACTION_LABEL}) WHERE a.address IS NOT NULL "
            "RETURN count(a) AS n, collect(keys(a))[0] AS sample_keys"
        ).single()
        if rec:
            logger.info("自检: 含地址的景点 %s, 样例属性 %s", rec["n"], rec["sample_keys"])
            if rec["n"] == 0:
                logger.error("自检失败: 没有任何 Attraction.address，请检查三元组与导入逻辑")
