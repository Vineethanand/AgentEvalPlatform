import re


def word_count(text):
    """Number of whitespace-separated words."""
    return len(text.split())


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"
