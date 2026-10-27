#!/usr/bin/env python3
# coding: utf-8
"""项目配置。始终从仓库根目录读取 .env。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    # src/sichuan_qa/config.py → 仓库根
    return Path(__file__).resolve().parents[2]


ROOT = project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"

    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash-ga-260731"
    llm_temperature: float = 0.2

    flask_host: str = "127.0.0.1"
    flask_port: int = 5000
    log_level: str = "INFO"

    triplet_csv: str = str(ROOT / "景点知识图谱_三元组.csv")
    raw_csv: str = str(ROOT / "完整数据爬取.csv")
    attraction_dict: str = str(ROOT / "dict" / "attraction_name.txt")
    golden_path: str = str(ROOT / "data" / "eval" / "golden.json")

    retrieve_top_k: int = 8
    near_limit: int = 3
    enable_text2cypher: bool = False

    @property
    def llm_enabled(self) -> bool:
        key = (self.llm_api_key or "").strip()
        return bool(key) and not key.lower().startswith("your_")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
