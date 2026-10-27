# coding: utf-8
"""不依赖 Neo4j / LLM 的离线单测。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sichuan_qa.nlu.understand import rule_understand
from sichuan_qa.rag.generator import template_answer
from sichuan_qa.rag.llm import llm_disabled
from sichuan_qa.rag.pipeline import apply_session, ask, is_out_of_scope
from sichuan_qa.rag.retriever import EvidenceItem, rank_score, sanitize_lucene


class TestRankScore(unittest.TestCase):
    def test_panda_beats_skydive(self):
        panda = EvidenceItem(
            name="成都大熊猫繁育研究基地",
            properties={"rating": 4.5, "popularity": 9.5},
        )
        sky = EvidenceItem(
            name="青城山skydive跳伞基地",
            properties={"rating": 5.0, "popularity": 3.3},
        )
        sub = EvidenceItem(
            name="成都大熊猫繁育研究基地-瞭望塔",
            properties={"rating": 5.0, "popularity": 2.9},
        )
        self.assertGreater(rank_score(panda), rank_score(sky))
        self.assertGreater(rank_score(panda), rank_score(sub))


class TestLucene(unittest.TestCase):
    def test_escapes_question_mark(self):
        self.assertIn(r"\?", sanitize_lucene("熊猫基地在哪?"))

    def test_empty_becomes_star(self):
        self.assertEqual("*", sanitize_lucene("   "))


class TestCityNotStolen(unittest.TestCase):
    def test_leshan_inside_buddha(self):
        plan = rule_understand("乐山大佛的地址在哪？")
        self.assertNotEqual("乐山", plan.city)

    def test_chengdu_recommend_keeps_city(self):
        plan = rule_understand("成都适合带小孩的景点有哪些？")
        self.assertEqual("成都", plan.city)


class TestFacilitiesIntent(unittest.TestCase):
    def test_facilities_fact(self):
        plan = rule_understand("成都大熊猫繁育研究基地有什么服务设施？")
        self.assertEqual("fact", plan.intent)
        self.assertIn("facilities", plan.attributes)


class TestRefuse(unittest.TestCase):
    def test_realtime_flag(self):
        self.assertTrue(is_out_of_scope("九寨沟明天还剩多少张门票可以买？"))
        self.assertFalse(is_out_of_scope("九寨沟门票多少钱？"))
        self.assertTrue(is_out_of_scope("北京故宫今天人多吗？"))

    def test_session_followup_keeps_entity(self):
        first = rule_understand("成都大熊猫繁育研究基地的地址在哪里？")
        follow = rule_understand("它的电话是多少？")
        follow = apply_session(follow, {"entities": first.entities, "city": first.city})
        self.assertEqual(first.entities, follow.entities)
        self.assertEqual("fact", follow.intent)
        self.assertIn("phone", follow.attributes)

    def test_session_does_not_steal_new_city_query(self):
        plan = rule_understand("成都适合带小孩的景点有哪些？")
        plan = apply_session(plan, {"entities": ["武侯祠"], "city": "成都"})
        self.assertEqual([], plan.entities)
        self.assertEqual("recommend", plan.intent)

    def test_ask_refuses_without_graph(self):
        with llm_disabled():
            result = ask("九寨沟明天还剩多少张门票可以买？")
        self.assertEqual("refuse", result.mode)
        self.assertIn("余票", result.answer)

    def test_template_empty(self):
        plan = rule_understand("不存在的景点xyz的地址")
        text = template_answer(plan, [])
        self.assertTrue("抱歉" in text or "没有" in text)

    def test_template_facilities(self):
        plan = rule_understand("成都大熊猫繁育研究基地有什么服务设施？")
        item = EvidenceItem(name="成都大熊猫繁育研究基地", facilities=["停车场", "餐饮"])
        text = template_answer(plan, [item])
        self.assertIn("停车场", text)

    def test_template_compare(self):
        plan = rule_understand("峨眉山和青城山哪个评分更高？")
        items = [
            EvidenceItem(name="峨眉山", city="乐山", properties={"rating": 4.8}),
            EvidenceItem(name="青城山", city="成都", properties={"rating": 4.6}),
        ]
        text = template_answer(plan, items)
        self.assertIn("峨眉山", text)
        self.assertIn("青城山", text)
        self.assertIn("4.8", text)

    def test_ask_refuses_out_of_region(self):
        result = ask("北京故宫今天人多吗？")
        self.assertEqual("refuse", result.mode)


if __name__ == "__main__":
    unittest.main()
