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


def doc_headings(*items, level=2):
    """Documento com títulos e parágrafos.

    Cada item é (nível, âncora, texto) para um título, ou str para um parágrafo.
    Também aceita uma lista única de itens. Se todos os itens forem str, cada um
    vira um título de `level` com âncora h-<posição>.
    """
    if len(items) == 1 and isinstance(items[0], list):
        items = tuple(items[0])
    if all(isinstance(i, str) for i in items):
        items = tuple((level, f"h-{n}", t) for n, t in enumerate(items))
    content = []
    for item in items:
        if isinstance(item, str):
            content.append({"type": "paragraph", "content": [_text(item)]})
        else:
            lvl, anchor, title = item
            content.append({"type": "heading", "attrs": {"level": lvl, "anchor": anchor},
                            "content": [_text(title)]})
    return {"type": "doc", "content": content}


def doc_mention(record_id, label, anchor=""):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "mention", "attrs": {"record": record_id, "anchor": anchor, "label": label}}]}]}


def doc_with_link(text, href):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [
        _text(text, [{"type": "link", "attrs": {"href": href}}])]}]}
