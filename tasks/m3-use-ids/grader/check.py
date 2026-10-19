"""Grader for m3-use-ids (memory chain M3, use step): ticket ids in the remembered format, lowest first."""
import re

EXPECTED = ["TKT-00007", "TKT-00099", "TKT-00318", "TKT-12045"]


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Collect every TKT-<digits> id in the reply (case-insensitive) and require the exact expected list.

    The ids are zero-padded to five digits, a format only the teach task showed, so bare numbers or a different
    padding fail. Comparing the whole list also checks the order and that no extra id was listed.
    """
    found = re.findall(r"TKT-\d+", final_answer or "", re.I)
    return [{"name": "ids in the remembered format, lowest first", "passed": [f.upper() for f in found] == EXPECTED,
             "detail": (final_answer or "").strip()[:200]}]
