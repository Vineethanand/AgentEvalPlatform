def word_count(text):
    """Number of whitespace-separated words."""
    return len(text.split())


def slugify(text):
    return text.lower().replace(" ", "-")
