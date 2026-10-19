"""Grader for changelog-house-format: the reply must be exactly one changelog entry in the house format.

The format is only described in the changelog-format skill, so an agent without the skill cannot match it.
"""
import re

EXPECTED = [
    "## 3.2.0 (2025-03-14)",
    "### Added", "- Add CSV export (#101)", "- Add dark mode (#107)",
    "### Changed", "- Default timeout is now 30s (#110)",
    "### Fixed", "- Crash when config is empty (#98)", "- Wrong totals on refunds (#104)",
]


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Compare the non-empty lines of the reply (code fences removed) with the expected entry, line by line."""
    text = re.sub(r"```(?:markdown|md)?", "", final_answer or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [
        {"name": "entry matches the house format exactly", "passed": lines == EXPECTED,
         "detail": "" if lines == EXPECTED else f"got {lines}"},
    ]
