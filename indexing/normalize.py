import unicodedata


def normalize(text) -> str:
    """Minúsculas e sem acentos."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
