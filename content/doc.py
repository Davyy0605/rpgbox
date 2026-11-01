"""Validação e extração sobre documentos Tiptap (JSON)."""
import re
import secrets
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

NODES = {"doc", "paragraph", "heading", "text", "bulletList", "orderedList",
         "listItem", "hardBreak", "mention"}
MARKS = {"bold", "italic", "link", "textStyle"}
SAFE_SCHEMES = {"http", "https", "mailto"}
MAX_DEPTH = 32
ANCHOR_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
SEP = " › "
_BAD_URL_CHARS = re.compile(r"[\x00-\x20\x7f-\x9f  ]")


def safe_href(href) -> bool:
    """True só para http(s) com host ou mailto, sem espaços nem controles."""
    if not isinstance(href, str) or not href or _BAD_URL_CHARS.search(href):
        return False
    try:
        parts = urlsplit(href)
    except ValueError:
        return False
    scheme = parts.scheme.lower()
    if scheme not in SAFE_SCHEMES:
        return False
    return bool(parts.path) if scheme == "mailto" else bool(parts.netloc)


def valid_color(color) -> bool:
    return isinstance(color, str) and COLOR_RE.fullmatch(color) is not None


def valid_anchor(anchor) -> bool:
    return isinstance(anchor, str) and ANCHOR_RE.fullmatch(anchor) is not None


def clean_text(value) -> bool:
    """False se a string tem NUL ou substitutos soltos (não cabem em JSON/UTF-8 do banco)."""
    if "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(msg):
    raise ValidationError(msg)


def _mark(mark):
    if not isinstance(mark, dict) or mark.get("type") not in MARKS:
        _fail("Marca não permitida.")
    if mark["type"] == "link":
        href = (mark.get("attrs") or {}).get("href")
        if not safe_href(href) or not clean_text(href):
            _fail("Endereço de link não permitido.")
        return {"type": "link", "attrs": {"href": href}}
    if mark["type"] == "textStyle":
        # Cor inválida descarta só a marca: o texto fica, sem erro para quem escreveu.
        attrs = mark.get("attrs")
        color = attrs.get("color") if isinstance(attrs, dict) else None
        return {"type": "textStyle", "attrs": {"color": color.lower()}} if valid_color(color) else None
    return {"type": mark["type"]}


def _node(node, depth):
    if depth > MAX_DEPTH:
        _fail("Documento aninhado demais.")
    if not isinstance(node, dict) or node.get("type") not in NODES:
        _fail("Nó não permitido.")
    kind = node["type"]
    attrs = node.get("attrs") or {}
    if not isinstance(attrs, dict):
        _fail("Atributos inválidos.")
    out = {"type": kind}
    if kind == "text":
        if not isinstance(node.get("text"), str):
            _fail("Texto inválido.")
        if not clean_text(node["text"]):
            _fail("Texto inválido.")
        out["text"] = node["text"]
        if node.get("marks"):
            if not isinstance(node["marks"], list):
                _fail("Marcas inválidas.")
            marks = [m for m in map(_mark, node["marks"]) if m]
            if marks:
                out["marks"] = marks
        return out
    if kind == "heading":
        level = attrs.get("level", 2)
        if not is_int(level) or not 1 <= level <= 6:
            _fail("Nível de título inválido.")
        anchor = attrs.get("anchor")
        if not anchor:
            anchor = "h-" + secrets.token_hex(4)
        elif not valid_anchor(anchor):
            _fail("Âncora inválida.")
        out["attrs"] = {"level": level, "anchor": anchor}
    elif kind == "mention":
        if not is_int(attrs.get("record")):
            _fail("Menção inválida.")
        anchor, label = attrs.get("anchor", ""), attrs.get("label", "")
        if anchor != "" and not valid_anchor(anchor):
            _fail("Âncora inválida.")
        if not isinstance(label, str) or not clean_text(label):
            _fail("Menção inválida.")
        out["attrs"] = {"record": attrs["record"], "anchor": anchor, "label": label}
    content = node.get("content")
    if content is not None:
        if not isinstance(content, list) or kind in ("mention", "hardBreak"):
            _fail("Conteúdo inválido.")
        # Nó de texto vazio não existe para o editor: com um deles, o documento não abriria.
        out["content"] = [_node(c, depth + 1) for c in content
                          if not (isinstance(c, dict) and c.get("type") == "text" and c.get("text") == "")]
    return out


def validate_doc(doc: dict) -> dict:
    """Devolve uma cópia normalizada ou lança ValidationError."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        _fail("Documento inválido.")
    return _node(doc, 0)


def as_doc(value) -> dict:
    """Valor de campo longo como documento; textos antigos viram um parágrafo."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": value}]}]}
    return {"type": "doc", "content": []}


def iter_nodes(doc):
    """Todos os nós, em pré-ordem, incluindo a raiz."""
    if not isinstance(doc, dict):
        return
    yield doc
    content = doc.get("content")
    if isinstance(content, list):
        for child in content:
            yield from iter_nodes(child)


def _inline_text(node):
    kind = node.get("type")
    if kind == "text":
        return node.get("text", "")
    if kind == "mention":
        return (node.get("attrs") or {}).get("label", "")
    if kind == "hardBreak":
        return " "
    return "".join(_inline_text(c) for c in node.get("content") or [] if isinstance(c, dict))


def _collect(node, out):
    if node.get("type") in ("paragraph", "heading", "text", "mention"):
        out.append(_inline_text(node))
        return
    for child in node.get("content") or []:
        if isinstance(child, dict):
            _collect(child, out)


def plain_text(doc) -> str:
    """Texto corrido: blocos separados por um espaço; menção vira o rótulo."""
    parts = []
    if isinstance(doc, dict):
        _collect(doc, parts)
    return " ".join(p for p in parts if p)


def headings(doc) -> list[tuple[str, str]]:
    return [((n.get("attrs") or {}).get("anchor", ""), _inline_text(n))
            for n in iter_nodes(doc)
            if n.get("type") == "heading" and (n.get("attrs") or {}).get("anchor")]
