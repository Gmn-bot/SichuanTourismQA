"""Neo4j 官方驱动封装。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase, Session

from sichuan_qa.config import get_settings
from sichuan_qa.logging_setup import get_logger

logger = get_logger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info("Neo4j driver created: %s", settings.neo4j_uri)
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def session_scope() -> Iterator[Session]:
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def run_query(cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        result = session.run(cypher, parameters or {})
        return [record.data() for record in result]


def verify_connectivity() -> None:
    get_driver().verify_connectivity()
