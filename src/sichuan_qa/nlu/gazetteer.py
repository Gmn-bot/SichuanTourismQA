"""景点实体链接：Aho-Corasick + 简称 + 最长匹配。"""

from __future__ import annotations

from pathlib import Path

import ahocorasick

from sichuan_qa.config import get_settings
from sichuan_qa.logging_setup import get_logger
from sichuan_qa.nlu.lexicon import ATTRACTION_ALIASES

logger = get_logger(__name__)


class Gazetteer:
    def __init__(self, names: list[str] | None = None, aliases: dict[str, str] | None = None):
        settings = get_settings()
        self.aliases = dict(ATTRACTION_ALIASES)
        if aliases:
            self.aliases.update(aliases)
        self.canonical = set(names or self._load_names(settings.attraction_dict))
        vocab = set(self.canonical) | set(self.aliases.keys())
        self.automaton = self._build(sorted(vocab, key=len, reverse=True))

    @staticmethod
    def _load_names(path: str) -> list[str]:
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("景点词典不存在: %s", path)
            return list(ATTRACTION_ALIASES.values())
        names = []
        with file_path.open(encoding="utf-8") as handle:
            for line in handle:
                name = line.strip()
                if name:
                    names.append(name)
        logger.info("加载景点词典 %s 条", len(names))
        return names

    @staticmethod
    def _build(words: list[str]) -> ahocorasick.Automaton:
        tree = ahocorasick.Automaton()
        for index, word in enumerate(words):
            if word:
                tree.add_word(word, (index, word))
        if words:
            tree.make_automaton()
        return tree

    def extract(self, text: str) -> list[str]:
        if not text:
            return []
        raw: list[str] = []
        for _, (_, word) in self.automaton.iter(text):
            raw.append(word)
        if not raw:
            return []
        nested = set()
        for left in raw:
            for right in raw:
                if left != right and left in right:
                    nested.add(left)
        final: list[str] = []
        seen: set[str] = set()
        for word in raw:
            if word in nested:
                continue
            full = self.aliases.get(word, word)
            if full not in seen:
                seen.add(full)
                final.append(full)
        return final


_gazetteer: Gazetteer | None = None


def get_gazetteer() -> Gazetteer:
    global _gazetteer
    if _gazetteer is None:
        _gazetteer = Gazetteer()
    return _gazetteer
