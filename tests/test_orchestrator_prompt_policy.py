from __future__ import annotations

import unittest

from limbi.prompt_policy import (
    extract_code_candidate,
    looks_like_actionable_code_task,
    needs_clarification,
)


class OrchestratorPromptPolicyTests(unittest.TestCase):
    def test_save_this_file_is_not_clarification(self) -> None:
        self.assertEqual(needs_clarification("save this file"), [])

    def test_fix_the_error_is_not_clarification(self) -> None:
        self.assertEqual(needs_clarification("fix the error in the code"), [])

    def test_actionable_code_task_is_detected(self) -> None:
        self.assertTrue(looks_like_actionable_code_task("save the code in this project directory"))

    def test_extract_code_candidate_from_fenced_block(self) -> None:
        content, language = extract_code_candidate(
            "Here is the code:\n```python\nprint('hello')\n```"
        )
        self.assertEqual(content, "print('hello')")
        self.assertEqual(language, "python")


if __name__ == "__main__":
    unittest.main()
