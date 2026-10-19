import re


def check(workspace, final_answer):
    m = re.findall(r"(\d{1,2}:\d{2})\s*[-\u2013]\s*(\d{1,2}:\d{2})", final_answer or "")
    got = [(a.zfill(5), b.zfill(5)) for a, b in m]
    return [{"name": "earliest common 60-minute slot is 16:00-17:00", "passed": got == [("16:00", "17:00")],
             "detail": (final_answer or "").strip()[:120]}]
