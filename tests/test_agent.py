# coding: utf-8
"""智能体工具封装单测，不强制调用 LLM。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sichuan_qa.nlu.understand import QueryPlan, rule_understand
from sichuan_qa.rag.agent import _canon_names, _langchain_tools
from sichuan_qa.rag.llm import llm_disabled
from sichuan_qa.rag.pipeline import ask
from sichuan_qa.rag.retriever import EvidenceItem


class TestAgentTools(unittest.TestCase):
    def test_tool_names(self):
        names = {t.name for t in _langchain_tools()}
        self.assertIn("lookup_fact_tool", names)
        self.assertIn("recommend_attractions_tool", names)
        self.assertIn("nearby_attractions_tool", names)
        self.assertIn("compare_attractions_tool", names)
        self.assertIn("search_open_tool", names)
        self.assertIn("get_weather_tool", names)
        self.assertIn("lookup_ticket_price_tool", names)
        self.assertIn("lookup_booking_status_tool", names)

    def test_canon_alias(self):
        names = _canon_names(["熊猫基地"])
        self.assertIn("成都大熊猫繁育研究基地", names)

    def test_llm_off_stays_pipeline(self):
        with llm_disabled():
            result = ask("北京故宫今天人多吗？")
        self.assertEqual("refuse", result.mode)
        self.assertEqual([], result.tools_used)

    def test_price_and_weather_not_refused(self):
        from sichuan_qa.rag.pipeline import is_out_of_scope, is_realtime_inventory

        self.assertFalse(is_out_of_scope("熊猫基地门票多少钱"))
        self.assertFalse(is_out_of_scope("成都今天天气怎么样"))
        self.assertTrue(is_realtime_inventory("熊猫基地明天还剩多少票"))
        self.assertTrue(is_realtime_inventory("熊猫基地还能买到票吗"))

    def test_lookup_uses_retriever(self):
        item = EvidenceItem(name="武侯祠", city="成都", properties={"address": "武侯祠大街231号"})
        with patch("sichuan_qa.rag.agent.retrieve", return_value=[item]):
            from sichuan_qa.rag.agent import _scratch, lookup_fact

            token = _scratch.set({"evidence": [], "tools": []})
            try:
                text = lookup_fact(["武侯祠"], ["address"])
            finally:
                _scratch.reset(token)
        self.assertIn("武侯祠", text)
        self.assertIn("231", text)

    def test_lookup_fact_accepts_chinese_attrs(self):
        captured: dict = {}
        item = EvidenceItem(name="武侯祠", properties={"opening_time": "08:00-18:00"})

        def fake_retrieve(plan):
            captured["attrs"] = plan.attributes
            return [item]

        with patch("sichuan_qa.rag.agent.retrieve", side_effect=fake_retrieve):
            from sichuan_qa.rag.agent import _scratch, lookup_fact

            token = _scratch.set({"evidence": [], "tools": []})
            try:
                lookup_fact(["武侯祠"], ["开放时间"])
            finally:
                _scratch.reset(token)
        self.assertEqual(["opening_time"], captured["attrs"])

    def test_weather_label(self):
        from sichuan_qa.rag.web_tools import weather_label

        self.assertEqual("晴", weather_label(0))
        self.assertEqual("小雨", weather_label(61))

    def test_get_weather_uses_open_meteo(self):
        from sichuan_qa.rag.agent import get_weather

        payload = {
            "current": {
                "temperature_2m": 18.5,
                "weather_code": 0,
                "relative_humidity_2m": 60,
                "wind_speed_10m": 4,
            },
            "daily": {
                "time": ["2026-10-27"],
                "weather_code": [0],
                "temperature_2m_max": [22],
                "temperature_2m_min": [12],
                "precipitation_probability_max": [10],
            },
        }
        with patch("sichuan_qa.rag.web_tools.http_get_json", return_value=payload):
            text = get_weather("成都")
        self.assertIn("联网天气", text)
        self.assertIn("晴", text)
        self.assertIn("18.5", text)

    def test_ticket_tool_combines_kg_and_web(self):
        item = EvidenceItem(
            name="成都大熊猫繁育研究基地",
            properties={"ticket_info": "成人票 55 元"},
        )
        with patch("sichuan_qa.rag.agent.retrieve", return_value=[item]), patch(
            "sichuan_qa.rag.agent.search_web_snippets",
            return_value="【联网检索摘要】官网票价约 55 元",
        ):
            from sichuan_qa.rag.agent import _scratch, lookup_ticket_price

            token = _scratch.set({"evidence": [], "tools": []})
            try:
                text = lookup_ticket_price("熊猫基地")
            finally:
                _scratch.reset(token)
        self.assertIn("55", text)
        self.assertIn("联网检索", text)
        self.assertIn("不是实时余票", text)

    def test_booking_status_has_no_inventory_number(self):
        item = EvidenceItem(
            name="成都大熊猫繁育研究基地",
            properties={"website": "https://www.panda.org.cn", "phone": "028-83510033"},
        )
        with patch("sichuan_qa.rag.agent.retrieve", return_value=[item]), patch(
            "sichuan_qa.rag.agent.search_web_snippets",
            return_value="【联网检索摘要】官网预约入口",
        ):
            from sichuan_qa.rag.agent import _scratch, lookup_booking_status

            token = _scratch.set({"evidence": [], "tools": []})
            try:
                text = lookup_booking_status("熊猫基地")
            finally:
                _scratch.reset(token)
        self.assertIn("没有景区订票库存接口", text)
        self.assertIn("panda.org.cn", text)
        self.assertNotRegex(text, r"还剩\s*\d+")

    def test_as_text_and_clip(self):
        from sichuan_qa.rag.agent import as_text, clip_text

        self.assertEqual("你好", as_text([{"text": "你好"}]))
        self.assertTrue(clip_text("a" * 400).endswith("…"))

    def test_react_loop_records_trace(self):
        class FakeAI:
            def __init__(self, content, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls or []

        class FakeTool:
            name = "lookup_fact_tool"

            def invoke(self, args):
                return "武侯祠的地址是：武侯祠大街231号"

        class FakeBound:
            def __init__(self):
                self.n = 0

            def invoke(self, messages):
                self.n += 1
                if self.n == 1:
                    return FakeAI(
                        "需要查地址",
                        [{"name": "lookup_fact_tool", "args": {"names": ["武侯祠"]}, "id": "c1"}],
                    )
                return FakeAI("武侯祠在武侯祠大街231号。", [])

        class FakeModel:
            def bind_tools(self, tools):
                return FakeBound()

        with patch("sichuan_qa.rag.llm.get_chat_model", return_value=FakeModel()), patch(
            "sichuan_qa.rag.agent._langchain_tools",
            return_value=[FakeTool()],
        ):
            from sichuan_qa.rag.agent import run_agent

            plan = QueryPlan(intent="fact", entities=["武侯祠"], raw_question="武侯祠地址")
            answer, _evidence, tools, trace = run_agent("武侯祠地址", plan)
        self.assertIn("武侯祠", answer)
        self.assertEqual(["lookup_fact_tool"], tools)
        self.assertEqual("需要查地址", trace[0]["thought"])
        self.assertEqual("lookup_fact_tool", trace[0]["actions"][0]["tool"])
        self.assertIn("231", trace[0]["actions"][0]["observation"])


class TestRulePlanForAgent(unittest.TestCase):
    def test_recommend_plan(self):
        plan = rule_understand("成都适合带小孩的景点有哪些？")
        self.assertEqual("recommend", plan.intent)
        self.assertIsInstance(plan, QueryPlan)


if __name__ == "__main__":
    unittest.main()
