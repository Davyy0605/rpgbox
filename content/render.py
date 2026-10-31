"""render_doc: único caminho do texto guardado até o HTML."""
import copy

from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString, mark_safe

from .doc import MAX_DEPTH, SEP, is_int, iter_nodes, safe_href, valid_anchor

_SIMPLE = {"paragraph": "p", "bulletList": "ul", "orderedList": "ol", "listItem": "li"}


def _mention_ids(doc):
    return sorted({(n.get("attrs") or {}).get("record") for n in iter_nodes(doc)
                   if n.get("type") == "mention" and is_int((n.get("attrs") or {}).get("record"))})


def _text(node):
    out = escape(node.get("text") if isinstance(node.get("text"), str) else "")
    for mark in node.get("marks") or []:
        if not isinstance(mark, dict):
            continue
        kind = mark.get("type")
        if kind == "bold":
            out = format_html("<strong>{}</strong>", out)
        elif kind == "italic":
            out = format_html("<em>{}</em>", out)
        elif kind == "link":
            href = (mark.get("attrs") or {}).get("href")
            if safe_href(href):
                out = format_html('<a href="{}" target="_blank" rel="noopener noreferrer nofollow">{}</a>',
                                  href, out)
    return out


def _mention(node, names):
    attrs = node.get("attrs") or {}
    record, anchor = attrs.get("record"), attrs.get("anchor") or ""
    name = names.get(record) if is_int(record) else None
    if name is None:
        return format_html("<s>{}</s>", attrs.get("label") if isinstance(attrs.get("label"), str) else "")
    href = reverse("record-detail", args=[record])
    panel = reverse("record-panel", args=[record])
    if valid_anchor(anchor):
        _, sep, heading = attrs.get("label", "").rpartition(SEP)
        name = f"{name}{sep}{heading}"
        return format_html('<a class="mention" href="{}?trecho={}#{}" data-panel-url="{}?ancora={}" '
                           'data-record="{}" data-anchor="{}">{}</a>',
                           href, anchor, anchor, panel, anchor, record, anchor, name)
    return format_html('<a class="mention" href="{}" data-panel-url="{}" data-record="{}">{}</a>',
                       href, panel, record, name)


def _children(node, names, depth):
    return mark_safe("".join(_node(c, names, depth + 1)
                             for c in node.get("content") or [] if isinstance(c, dict)))


def _node(node, names, depth):
    if depth > MAX_DEPTH:
        return ""
    kind = node.get("type")
    if kind == "text":
        return _text(node)
    if kind == "mention":
        return _mention(node, names)
    if kind == "hardBreak":
        return mark_safe("<br>")
    if kind == "doc":
        return _children(node, names, depth)
    if kind in _SIMPLE:
        return format_html("<{0}>{1}</{0}>", _SIMPLE[kind], _children(node, names, depth))
    if kind == "heading":
        attrs = node.get("attrs") or {}
        level = attrs.get("level")
        level = level if is_int(level) and 1 <= level <= 6 else 2
        inner = _children(node, names, depth)
        if valid_anchor(attrs.get("anchor")):
            return format_html('<h{0} id="{1}">{2}</h{0}>', level, attrs["anchor"], inner)
        return format_html("<h{0}>{1}</h{0}>", level, inner)
    return ""  # nó desconhecido: descartado, nunca emitido


def editor_doc(doc, resolve) -> tuple[dict, list[int]]:
    """Cópia para o editor com os nomes atuais nas menções, e os ids de destinos apagados."""
    out = copy.deepcopy(doc)
    ids = _mention_ids(out)
    names = resolve(ids) if ids else {}
    for node in iter_nodes(out):
        attrs = node.get("attrs") or {}
        name = names.get(attrs.get("record")) if node.get("type") == "mention" else None
        if name is not None:
            _, sep, heading = attrs.get("label", "").rpartition(SEP)
            attrs["label"] = f"{name}{sep}{heading}" if sep and attrs.get("anchor") else name
    return out, [i for i in ids if i not in names]


def render_doc(doc, resolve) -> SafeString:
    """HTML seguro; `resolve(ids)` devolve {id: nome atual} dos registros que ainda existem."""
    if not isinstance(doc, dict):
        return mark_safe("")
    ids = _mention_ids(doc)
    names = resolve(ids) if ids else {}
    return mark_safe(_node(doc, names, 0))
