import re

EXPECTED = [
    "## 3.2.0 (2025-03-14)",
    "### Added", "- Add CSV export (#101)", "- Add dark mode (#107)",
    "### Changed", "- Default timeout is now 30s (#110)",
    "### Fixed", "- Crash when config is empty (#98)", "- Wrong totals on refunds (#104)",
]


def check(workspace, final_answer):
    text = re.sub(r"```(?:markdown|md)?", "", final_answer or "")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return [
        {"name": "entry matches the house format exactly", "passed": lines == EXPECTED,
         "detail": "" if lines == EXPECTED else f"got {lines}"},
    ]
