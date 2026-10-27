"""可插拔 Chat 模型（OpenAI 兼容网关：DeepSeek / 通义 / 星火兼容模式）。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from sichuan_qa.config import get_settings
from sichuan_qa.logging_setup import get_logger

logger = get_logger(__name__)

_llm_disabled = ContextVar("sichuan_qa_llm_disabled", default=False)


def llm_available() -> bool:
    if _llm_disabled.get():
        return False
    return get_settings().llm_enabled


@contextmanager
def llm_disabled():
    """评测时关闭 LLM，只衡量图谱检索 + 模板。"""
    token = _llm_disabled.set(True)
    try:
        yield
    finally:
        _llm_disabled.reset(token)


@lru_cache(maxsize=1)
def get_chat_model():
    if not llm_available():
        return None
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("未安装 langchain-openai，LLM 功能关闭")
        return None

    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        temperature=settings.llm_temperature,
        timeout=60,
        max_retries=2,
    )
