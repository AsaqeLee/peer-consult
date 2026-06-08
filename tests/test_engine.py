import unittest
from peer_consult.engine import decision_draft

class TestEngineConsensus(unittest.TestCase):
    def test_decision_draft_consensus(self):
        summary = {
            "claude": {
                "recommended_option": "Fix Bug A",
                "options": [{"name": "Fix Bug A", "tests": ["test1"], "risks": [], "pros": [], "cons": []}]
            },
            "gemini": {
                "recommended_option": "Fix Bug A",
                "options": [{"name": "Fix Bug A", "tests": ["test1"], "risks": [], "pros": [], "cons": []}]
            },
            "codex_auto": {
                "root_causes_common": ["logic error"],
                "option_names_common": ["Fix Bug A"]
            }
        }
        result = decision_draft(summary)
        self.assertEqual(result["choice"], "Fix Bug A")
        self.assertIn("两侧推荐一致", result["choice_reason"])

    def test_decision_draft_claude_failure(self):
        summary = {
            "claude": {"error": "Timeout"},
            "gemini": {
                "recommended_option": "Option G",
                "options": [{"name": "Option G", "tests": ["tg1"], "risks": [], "pros": [], "cons": []}]
            },
            "codex_auto": {}
        }
        result = decision_draft(summary)
        self.assertEqual(result["choice"], "Option G")
        self.assertIn("Claude 侧失败", result["choice_reason"])

    def test_decision_draft_verifiability_priority(self):
        # Claude has 1 test, Gemini has 2 tests. Gemini should be picked.
        summary = {
            "claude": {
                "recommended_option": "Option C",
                "options": [{"name": "Option C", "tests": ["tc1"], "risks": [], "pros": [], "cons": []}]
            },
            "gemini": {
                "recommended_option": "Option G",
                "options": [{"name": "Option G", "tests": ["tg1", "tg2"], "risks": [], "pros": [], "cons": []}]
            },
            "codex_auto": {}
        }
        result = decision_draft(summary)
        self.assertEqual(result["choice"], "Option G")
        self.assertIn("以可验证性优先", result["choice_reason"])
        self.assertIn("Gemini", result["choice_reason"])

    def test_decision_draft_risk_priority(self):
        # Same number of tests, but Claude has fewer risks. Claude should be picked.
        summary = {
            "claude": {
                "recommended_option": "Option C",
                "options": [{"name": "Option C", "tests": ["t1"], "risks": ["r1"], "pros": [], "cons": []}]
            },
            "gemini": {
                "recommended_option": "Option G",
                "options": [{"name": "Option G", "tests": ["t1"], "risks": ["r1", "r2"], "pros": [], "cons": []}]
            },
            "codex_auto": {}
        }
        result = decision_draft(summary)
        self.assertEqual(result["choice"], "Option C")
        self.assertIn("以风险最小优先", result["choice_reason"])
        self.assertIn("Claude", result["choice_reason"])

if __name__ == "__main__":
    unittest.main()
