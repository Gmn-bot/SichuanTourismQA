"""黄金集评测。"""

from __future__ import annotations

import json
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from sichuan_qa.config import ROOT, get_settings
from sichuan_qa.logging_setup import get_logger
from sichuan_qa.rag.pipeline import ask

logger = get_logger(__name__)


def _load_golden(path: str | None) -> list[dict[str, Any]]:
    file_path = Path(path or get_settings().golden_path)
    if not file_path.exists():
        raise FileNotFoundError(f"黄金集不存在: {file_path}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def _hit(item: dict[str, Any], result) -> bool:
    expect_type = item.get("type", "fact")
    answer = result.answer or ""
    sources = {s.name for s in result.evidence}

    if expect_type == "refuse":
        if result.mode == "refuse":
            return True
        refuse_ok = "暂无" in answer or "没有" in answer or "抱歉" in answer or "无法" in answer
        invented = any(word in answer for word in ("明天一定", "剩余票数", "还能买到"))
        return refuse_ok and not invented

    names = item.get("expect_names") or []
    if names:
        matched = [name for name in names if name in sources or name in answer]
        if expect_type == "compare":
            return len(matched) == len(names)
        return bool(matched)

    contains = item.get("expect_contains") or []
    if contains:
        return all(token in answer for token in contains)
    return bool(result.evidence)


DEFAULT_REPORT = ROOT / "data" / "eval" / "latest.json"


def run_eval(
    path: str | None = None,
    *,
    use_llm: bool = False,
    out_path: str | None = None,
) -> dict[str, Any]:
    from sichuan_qa.rag.llm import llm_disabled

    golden = _load_golden(path)
    rows: list[dict[str, Any]] = []
    success = 0
    t0 = time.perf_counter()
    context = nullcontext() if use_llm else llm_disabled()
    with context:
        for item in golden:
            q = item["question"]
            started = time.perf_counter()
            try:
                result = ask(q)
                ok = _hit(item, result)
                rows.append(
                    {
                        "id": item.get("id"),
                        "question": q,
                        "type": item.get("type"),
                        "ok": ok,
                        "mode": result.mode,
                        "intent": result.plan.intent,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                        "answer_preview": (result.answer or "")[:120],
                        "sources": [e.name for e in result.evidence[:5]],
                    }
                )
                success += int(ok)
            except Exception as exc:
                rows.append(
                    {
                        "id": item.get("id"),
                        "question": q,
                        "type": item.get("type"),
                        "ok": False,
                        "error": str(exc),
                    }
                )
    total = len(golden) or 1
    latencies = [row["latency_ms"] for row in rows if "latency_ms" in row]
    by_type: dict[str, dict[str, int]] = {}
    for item, row in zip(golden, rows):
        bucket = by_type.setdefault(item.get("type", "unknown"), {"n": 0, "ok": 0})
        bucket["n"] += 1
        bucket["ok"] += int(bool(row.get("ok")))
    report = {
        "total": len(golden),
        "passed": success,
        "accuracy": round(success / total, 3),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "use_llm": use_llm,
        "by_type": by_type,
        "failed": [row["id"] for row in rows if not row.get("ok")],
        "cases": rows,
    }
    target = Path(out_path) if out_path else DEFAULT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(target)
    logger.info("评测完成 %s/%s，报告 %s", success, len(golden), target)
    return report

