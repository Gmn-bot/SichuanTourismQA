"""FastAPI 服务。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sichuan_qa.config import ROOT
from sichuan_qa.logging_setup import get_logger
from sichuan_qa.rag.pipeline import ask

logger = get_logger(__name__)

app = FastAPI(title="四川旅游 GraphRAG", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATE = ROOT / "templates" / "chat.html"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str | None = None


@app.get("/health")
def health() -> dict:
    neo4j = "unknown"
    try:
        from sichuan_qa.kg.connection import verify_connectivity

        verify_connectivity()
        neo4j = "ok"
    except Exception as exc:
        neo4j = f"error: {exc}"
    return {"status": "ok" if neo4j == "ok" else "degraded", "neo4j": neo4j}


@app.post("/api/ask")
def api_ask(body: AskRequest) -> dict:
    try:
        result = ask(body.question, session_id=body.session_id)
        return result.to_dict()
    except Exception as exc:
        logger.exception("问答失败")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    if TEMPLATE.exists():
        return TEMPLATE.read_text(encoding="utf-8")
    return "<h1>四川旅游 GraphRAG</h1><p>缺少 templates/chat.html</p>"
