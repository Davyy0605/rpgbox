"""Exportação de um documento para Markdown (sem escapar caracteres especiais)."""
from .doc import safe_href
from .render import editor_doc


def _inline(node):
    kind = node.get("type")
    if kind == "text":
        out = node.get("text", "")
        for mark in node.get("marks") or []:
            if mark.get("type") == "bold":
                out = f"**{out}**"
            elif mark.get("type") == "italic":
                out = f"*{out}*"
            elif mark.get("type") == "link":
                href = (mark.get("attrs") or {}).get("href")
                if safe_href(href):
                    out = f"[{out}]({href})"
        return out
    if kind == "mention":
        return (node.get("attrs") or {}).get("label", "")
    if kind == "hardBreak":
        return "  \n"
    return "".join(_inline(c) for c in node.get("content") or [])


def _block(node):
    kind = node.get("type")
    if kind == "heading":
        level = (node.get("attrs") or {}).get("level", 2)
        return "#" * level + " " + _inline(node)
    if kind in ("bulletList", "orderedList"):
        lines = []
        for n, item in enumerate(node.get("content") or [], 1):
            body = "\n".join(_block(c) for c in item.get("content") or [])
            prefix = "- " if kind == "bulletList" else f"{n}. "
            first, *rest = body.split("\n")
            lines.append(prefix + first)
            lines.extend(" " * len(prefix) + r for r in rest)
        return "\n".join(lines)
    return _inline(node)


def doc_to_markdown(doc, resolve=None) -> str:
    if resolve:  # nomes atuais nas menções
        doc, _ = editor_doc(doc, resolve)
    blocks = [_block(n) for n in doc.get("content") or []]
    return "\n\n".join(blocks) + "\n" if blocks else ""
