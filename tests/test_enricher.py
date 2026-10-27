# coding: utf-8
"""增强规则单测，不依赖 Neo4j。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sichuan_qa.kg.enricher import build_near_pairs, infer_tags, infer_ticket, parse_facilities


class TestEnricher(unittest.TestCase):
    def test_panda_tags(self):
        tags = infer_tags("成都大熊猫繁育研究基地", "可以近距离看大熊猫", 4.7)
        self.assertIn("亲子", tags)
        self.assertIn("自然", tags)
        self.assertIn("高分", tags)

    def test_intro_panda_does_not_tag_skydive(self):
        tags = infer_tags("青城山skydive跳伞基地", "可以看熊猫和青城山", 5.0)
        self.assertNotIn("亲子", tags)
        self.assertNotIn("动物", tags)

    def test_temple_tags(self):
        tags = infer_tags("武侯祠", "成都著名历史遗迹")
        self.assertIn("人文", tags)
        self.assertIn("历史", tags)

    def test_facilities_split(self):
        text = "停车场：有\n餐饮：有；卫生间：有"
        names = parse_facilities(text)
        self.assertIn("停车场", names)
        self.assertIn("餐饮", names)

    def test_ticket_free(self):
        info, is_free = infer_ticket("景区免费开放，无需门票")
        self.assertTrue(is_free)
        self.assertIsNotNone(info)

    def test_near_pairs(self):
        attractions = [
            {"name": "A", "rating": 4.8, "tags": ["亲子"]},
            {"name": "B", "rating": 4.6, "tags": ["亲子"]},
            {"name": "C", "rating": 3.1, "tags": ["人文"]},
        ]
        city_of = {"A": "成都", "B": "成都", "C": "成都"}
        pairs = build_near_pairs(attractions, city_of, limit=2)
        ends = {(a, b) for a, b, _ in pairs}
        self.assertIn(("A", "B"), ends)


if __name__ == "__main__":
    unittest.main()
