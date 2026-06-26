import re
import unicodedata

ARTICLES = {"the", "a", "an"}


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"\((tm|r|c)\)", " ", text)
    text = re.sub(r"[\u2122\u00ae\u00a9]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [word for word in text.split() if word not in ARTICLES]
    return " ".join(words)
