import re

EXPECTED = ["TKT-00007", "TKT-00099", "TKT-00318", "TKT-12045"]


def check(workspace, final_answer):
    found = re.findall(r"TKT-\d+", final_answer or "", re.I)
    return [{"name": "ids in the remembered format, lowest first", "passed": [f.upper() for f in found] == EXPECTED,
             "detail": (final_answer or "").strip()[:200]}]
