"""promptshape —— 自检测试。

识别提示词里的角色设定、任务、约束、示例与输出格式，标出缺失项与冲突项。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import promptshape  # noqa: E402


class TestPromptShape(unittest.TestCase):
    def test_full_prompt_has_all_slots(self):
        text = ("你是客服助手。\n"
                "请回答用户的问题。\n"
                "不要编造信息。\n"
                "例如：输入「怎么退款」，输出「走退款流程」。\n"
                "输出格式：JSON。")
        r = promptshape.analyze(text)
        self.assertEqual(r["missing_required"], [])
        self.assertEqual(r["conflicts"], [])
        self.assertEqual(r["coverage"]["filled"], 5)

    def test_missing_role_is_reported(self):
        r = promptshape.analyze("请帮我总结这段文字。不要编造。")
        self.assertIn("role", r["missing_required"])

    def test_conflict_is_found(self):
        r = promptshape.analyze("你是助手。只用一句话回答。\n输出格式：JSON，至少三段。")
        self.assertTrue(r["conflicts"])
        self.assertIn("a", r["conflicts"][0])
        self.assertIn("b", r["conflicts"][0])

    def test_does_not_modify_input(self):
        """防呆：只拆结构，不改写用户的提示词。"""
        text = "你是助手。请回答。输出 JSON。"
        before = text
        promptshape.analyze(text)
        self.assertEqual(text, before)

    def test_empty_text(self):
        r = promptshape.analyze("")
        self.assertEqual(r["sentence_count"], 0)
