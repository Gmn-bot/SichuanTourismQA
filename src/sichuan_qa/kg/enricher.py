"""离线图谱增强：标签、设施、票价线索、同城相关。"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

TAG_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"熊猫"), ["亲子", "自然", "动物"]),
    (re.compile(r"寺|庙|祠|堂|观|教堂|清真寺"), ["人文", "历史", "宗教"]),
    (re.compile(r"古镇|古街|古巷|宽窄|锦里"), ["人文", "街区"]),
    (re.compile(r"山|峡|沟|湖|瀑|森林|湿地|草原|雪山|冰川"), ["自然", "户外"]),
    (re.compile(r"博物馆|纪念馆|美术馆|展览"), ["人文", "展览"]),
    (re.compile(r"乐园|欢乐谷|迪士尼|水上乐园|嘉年华"), ["游乐", "亲子"]),
    (re.compile(r"温泉"), ["休闲"]),
    (re.compile(r"大佛"), ["人文", "历史", "宗教"]),
    (re.compile(r"遗址|故居|古城|城墙"), ["人文", "历史"]),
    (re.compile(r"公园"), ["休闲", "户外"]),
    (re.compile(r"夜市|夜景|灯光秀"), ["夜游"]),
    (re.compile(r"美食|火锅|小吃"), ["美食"]),
]

FREE_PATTERN = re.compile(r"免费开放|免费参观|免门票|无需门票")
PRICE_PATTERN = re.compile(r"(成人[^。；;\n]{0,12}?(\d+(?:\.\d+)?)\s*元)|门票[^。；;\n]{0,12}?(\d+(?:\.\d+)?)\s*元")
FACILITY_SPLIT = re.compile(r"[\n；;、|/]+")


def infer_tags(name: str, introduction: str = "", rating: float | None = None) -> list[str]:
    # 只在景点名上打标签，避免简介里提到「熊猫/山」就把跳伞店标成亲子
    text = name or ""
    tags: set[str] = set()
    for pattern, values in TAG_RULES:
        if pattern.search(text):
            tags.update(values)
    if rating is not None:
        try:
            if float(rating) >= 4.5:
                tags.add("高分")
        except (TypeError, ValueError):
            pass
    return sorted(tags)


def parse_facilities(facilities_text: str | None) -> list[str]:
    if not facilities_text:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for chunk in FACILITY_SPLIT.split(str(facilities_text)):
        chunk = chunk.strip()
        if not chunk:
            continue
        name = re.split(r"[：:]", chunk, maxsplit=1)[0].strip()
        name = re.sub(r"\s+", "", name)
        if len(name) < 2 or len(name) > 12:
            continue
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= 12:
            break
    return names


def infer_ticket(discount_policy: str | None, introduction: str = "") -> tuple[str | None, bool]:
    text = f"{discount_policy or ''} {introduction or ''}"
    is_free = bool(FREE_PATTERN.search(text))
    ticket_info = None
    match = PRICE_PATTERN.search(text)
    if match:
        ticket_info = match.group(0).strip()
    elif is_free:
        ticket_info = "免费开放（来自政策/简介文本，可能有条件）"
    return ticket_info, is_free


def enrich_attraction(record: dict[str, Any]) -> dict[str, Any]:
    """为单个景点字典补 tags / facilities / ticket_info / is_free。"""
    rating = record.get("rating")
    tags = infer_tags(record.get("name", ""), record.get("introduction", "") or "", rating)
    if record.get("is_free") or (record.get("ticket_info") and "免费" in str(record.get("ticket_info"))):
        tags = sorted(set(tags) | {"免费"})
    ticket_info, is_free = infer_ticket(record.get("discount_policy"), record.get("introduction", "") or "")
    if is_free:
        tags = sorted(set(tags) | {"免费"})
    facilities = parse_facilities(record.get("facilities_text"))
    record = dict(record)
    record["tags"] = tags
    record["facilities"] = facilities
    if ticket_info:
        record["ticket_info"] = ticket_info
    record["is_free"] = bool(is_free)
    return record


def build_near_pairs(
    attractions: list[dict[str, Any]],
    city_of: dict[str, str],
    limit: int = 3,
) -> list[tuple[str, str, str]]:
    """同城且共享标签（否则同城高分）的 NEAR 边。"""
    by_city: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in attractions:
        city = city_of.get(item["name"])
        if city:
            by_city[city].append(item)

    pairs: list[tuple[str, str, str]] = []
    for city, members in by_city.items():
        ranked = sorted(members, key=lambda x: float(x.get("rating") or 0), reverse=True)
        tag_index: dict[str, list[str]] = defaultdict(list)
        for item in ranked:
            for tag in item.get("tags") or []:
                tag_index[tag].append(item["name"])

        for item in members:
            name = item["name"]
            candidates: list[str] = []
            seen = {name}
            for tag in item.get("tags") or []:
                for other in tag_index.get(tag, []):
                    if other not in seen:
                        seen.add(other)
                        candidates.append(other)
                    if len(candidates) >= limit:
                        break
                if len(candidates) >= limit:
                    break
            if len(candidates) < limit:
                for other in ranked:
                    other_name = other["name"]
                    if other_name not in seen:
                        seen.add(other_name)
                        candidates.append(other_name)
                    if len(candidates) >= limit:
                        break
            reason = "same_city_tag" if item.get("tags") else "same_city_rating"
            for other_name in candidates[:limit]:
                pairs.append((name, other_name, reason))
    return pairs
