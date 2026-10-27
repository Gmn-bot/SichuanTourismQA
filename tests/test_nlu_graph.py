# coding: utf-8
"""NLU 规则回退单测。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sichuan_qa.nlu.gazetteer import Gazetteer
from sichuan_qa.nlu.understand import rule_understand


class TestGazetteer(unittest.TestCase):
    def setUp(self):
        self.g = Gazetteer(
            names=["成都大熊猫繁育研究基地", "武侯祠", "锦里古街"],
            aliases={"熊猫基地": "成都大熊猫繁育研究基地", "锦里": "锦里古街"},
        )

    def test_alias_and_longest(self):
        names = self.g.extract("熊猫基地的地址在哪")
        self.assertEqual(["成都大熊猫繁育研究基地"], names)

    def test_nested_name(self):
        names = self.g.extract("我想去锦里古街")
        self.assertEqual(["锦里古街"], names)


class TestRuleUnderstand(unittest.TestCase):
    def test_fact_address(self):
        plan = rule_understand("成都大熊猫繁育研究基地的地址在哪里？")
        self.assertEqual("fact", plan.intent)
        self.assertIn("address", plan.attributes)
        self.assertIn("成都大熊猫繁育研究基地", plan.entities)

    def test_recommend_city(self):
        plan = rule_understand("成都适合带小孩的景点有哪些？")
        self.assertEqual("recommend", plan.intent)
        self.assertEqual("成都", plan.city)
        self.assertIn("亲子", plan.tags)

    def test_alias_entity(self):
        plan = rule_understand("熊猫基地的电话是多少？")
        self.assertIn("成都大熊猫繁育研究基地", plan.entities)
        self.assertIn("phone", plan.attributes)

    def test_compare_two_mountains(self):
        plan = rule_understand("峨眉山和青城山哪个评分更高？")
        self.assertEqual("compare", plan.intent)
        self.assertIn("峨眉山", plan.entities)
        self.assertIn("青城山", plan.entities)

    def test_nearby_is_recommend(self):
        plan = rule_understand("去了武侯祠还可以去哪些附近景点？")
        self.assertEqual("recommend", plan.intent)
        self.assertIn("武侯祠", plan.entities)


if __name__ == "__main__":
    unittest.main()
