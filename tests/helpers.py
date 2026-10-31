"""Construtores de documentos Tiptap para os testes."""


def _text(text, marks=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def doc(*paragraphs):
    """doc("a", "b") -> documento com um parágrafo por texto."""
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [_text(p)] if p else []} for p in paragraphs]}


def doc_headings(*titles, level=2):
    """Documento só com títulos; o anchor de cada um é h-<posição>."""
    return {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": level, "anchor": f"h-{i}"}, "content": [_text(t)]}
        for i, t in enumerate(titles)]}


def doc_mention(record_id, label, anchor=""):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "mention", "attrs": {"record": record_id, "anchor": anchor, "label": label}}]}]}


def doc_with_link(text, href):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [
        _text(text, [{"type": "link", "attrs": {"href": href}}])]}]}
