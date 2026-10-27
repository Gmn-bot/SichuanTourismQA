#!/usr/bin/env python3
# coding: utf-8
"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 保证未安装包时也能从仓库根运行
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sichuan_qa.config import get_settings
from sichuan_qa.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


def cmd_import(args: argparse.Namespace) -> None:
    from sichuan_qa.kg.importer import import_knowledge_graph

    stats = import_knowledge_graph(csv_path=args.file, clear=args.clear)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_chat(_: argparse.Namespace) -> None:
    from sichuan_qa.rag.pipeline import ask

    print("四川文旅咨询助手 · 智能体 + Neo4j GraphRAG（输入 quit 退出）")
    while True:
        try:
            question = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"quit", "exit", "退出"}:
            break
        result = ask(question, session_id="cli")
        tools = f" tools={','.join(result.tools_used)}" if result.tools_used else ""
        print(f"助手[{result.mode}/{result.plan.intent}{tools}]: {result.answer}")
        for step in result.trace:
            thought = step.get("thought")
            if thought:
                print(f"  思考: {thought}")
            for action in step.get("actions") or []:
                print(f"  行动: {action.get('tool')}")
        if result.evidence:
            names = "、".join(item.name for item in result.evidence[:5])
            print(f"来源: {names}")
        print("-" * 40)


def cmd_web(args: argparse.Namespace) -> None:
    import uvicorn

    settings = get_settings()
    host = args.host or settings.web_host
    port = args.port or settings.web_port
    print(f"浏览器打开 http://127.0.0.1:{port}  （不要用 0.0.0.0）")
    uvicorn.run("sichuan_qa.api.app:app", host=host, port=port, reload=False)


def cmd_eval(args: argparse.Namespace) -> None:
    from sichuan_qa.eval.run_eval import run_eval

    report = run_eval(args.file, use_llm=args.llm, out_path=args.out)
    summary = {
        "total": report["total"],
        "passed": report["passed"],
        "accuracy": report["accuracy"],
        "elapsed_sec": report["elapsed_sec"],
        "avg_latency_ms": report["avg_latency_ms"],
        "use_llm": report["use_llm"],
        "by_type": report["by_type"],
        "failed": report["failed"],
        "report_path": report["report_path"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="四川文旅咨询助手（智能体 + Neo4j GraphRAG）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="导入并增强知识图谱")
    p_import.add_argument("--file", type=str, default=None, help="三元组 CSV")
    p_import.add_argument("--clear", action="store_true", help="导入前清空数据库")
    p_import.set_defaults(func=cmd_import)

    p_chat = sub.add_parser("chat", help="命令行问答")
    p_chat.set_defaults(func=cmd_chat)

    p_web = sub.add_parser("web", help="启动 FastAPI")
    p_web.add_argument("--host", type=str, default=None)
    p_web.add_argument("--port", type=int, default=None)
    p_web.set_defaults(func=cmd_web)

    p_eval = sub.add_parser("eval", help="跑黄金集评测")
    p_eval.add_argument("--file", type=str, default=None)
    p_eval.add_argument("--out", type=str, default=None, help="报告 JSON 路径")
    p_eval.add_argument("--llm", action="store_true", help="评测时启用 LLM（默认关闭，只测检索+模板）")
    p_eval.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        logger.exception("命令失败")
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
