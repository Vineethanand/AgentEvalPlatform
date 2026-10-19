"""Grader for meeting-slots: the reply must name the earliest common 60-minute free slot."""
import re


def check(workspace, final_answer):  # pylint: disable=unused-argument
    """Find every "HH:MM-HH:MM" range in the reply (hyphen or en dash) and require exactly 16:00-17:00.

    Times are zero-padded first so "9:00" and "09:00" compare equal. Requiring exactly one range means an
    answer that lists several candidate slots fails.
    """
    m = re.findall(r"(\d{1,2}:\d{2})\s*[-\u2013]\s*(\d{1,2}:\d{2})", final_answer or "")
    got = [(a.zfill(5), b.zfill(5)) for a, b in m]
    return [{"name": "earliest common 60-minute slot is 16:00-17:00", "passed": got == [("16:00", "17:00")],
             "detail": (final_answer or "").strip()[:120]}]
