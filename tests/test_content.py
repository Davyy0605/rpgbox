import re

import pytest
from django.core.exceptions import ValidationError
from django.utils.safestring import SafeString

from content.doc import headings, iter_nodes, plain_text, validate_doc
from content.markdown import doc_to_markdown
from content.render import render_doc
from records.sections import section

from .helpers import _text, doc, doc_headings, doc_mention, doc_with_link


def test_render_escapes_html():
    out = render_doc(doc("<script>alert(1)</script>"), lambda ids: {})
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert isinstance(out, SafeString)


def test_empty_text_nodes_are_dropped_because_the_editor_refuses_them():
    empty = {"type": "text", "text": ""}
    d = {"type": "doc", "content": [{"type": "paragraph", "content": [empty, _text("a"), empty]},
                                    {"type": "paragraph", "content": [empty]}]}
    assert validate_doc(d) == {"type": "doc", "content": [{"type": "paragraph", "content": [_text("a")]},
                                                          {"type": "paragraph", "content": []}]}


def test_rejects_unknown_node_and_javascript_url():
    with pytest.raises(ValidationError):
        validate_doc({"type": "doc", "content": [{"type": "iframe"}]})
    with pytest.raises(ValidationError):
        validate_doc(doc_with_link("x", "javascript:alert(1)"))


@pytest.mark.parametrize("href", [" JaVaScript:alert(1)", "java\tscript:alert(1)", "data:text/html,x",
                                  "/relativo", "//evil.com", "vbscript:x", ""])
def test_rejects_bad_hrefs(href):
    with pytest.raises(ValidationError):
        validate_doc(doc_with_link("x", href))


@pytest.mark.parametrize("href", ["http://a.com", "https://a.com/x?y=1", "mailto:a@b.com"])
def test_accepts_good_hrefs(href):
    validate_doc(doc_with_link("x", href))


def test_rejects_unknown_mark_and_malformed():
    bad = {"type": "doc", "content": [{"type": "paragraph", "content": [_text("a", [{"type": "underline"}])]}]}
    with pytest.raises(ValidationError):
        validate_doc(bad)
    for junk in (None, [], "x", {"type": "paragraph"}, {"type": "doc", "content": "x"}):
        with pytest.raises(ValidationError):
            validate_doc(junk)


def test_rejects_non_int_mention_record():
    with pytest.raises(ValidationError):
        validate_doc(doc_mention("5; drop", "x"))
    with pytest.raises(ValidationError):
        validate_doc(doc_mention(True, "x"))


def test_validate_generates_missing_heading_anchor():
    d = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [_text("T")]}]}
    out = validate_doc(d)
    assert re.fullmatch(r"h-[0-9a-f]{8}", out["content"][0]["attrs"]["anchor"])
    assert "anchor" not in d["content"][0]["attrs"]  # entrada não é mutada


def test_validate_keeps_existing_anchor_and_empty_doc_ok():
    assert validate_doc(doc_headings([(2, "a", "A")]))["content"][0]["attrs"]["anchor"] == "a"
    validate_doc({"type": "doc", "content": []})
    validate_doc({"type": "doc"})


def test_validate_rejects_bad_anchor_and_level():
    with pytest.raises(ValidationError):
        validate_doc(doc_headings([(2, 'a"><script>', "A")]))
    with pytest.raises(ValidationError):
        validate_doc(doc_headings([(9, "a", "A")]))


def test_validate_rejects_too_deep():
    node = {"type": "paragraph"}
    for _ in range(100):
        node = {"type": "bulletList", "content": [{"type": "listItem", "content": [node]}]}
    with pytest.raises(ValidationError):
        validate_doc({"type": "doc", "content": [node]})


def test_mention_uses_current_name():
    html = render_doc(doc_mention(5, "Antigo"), lambda ids: {5: "Novo"})
    assert "Novo" in html and "Antigo" not in html and 'data-record="5"' in html


def test_mention_to_deleted_record_is_struck_text():
    html = render_doc(doc_mention(5, "Kael"), lambda ids: {})
    assert "<s>Kael</s>" in html and "<a" not in html


def test_mention_with_anchor_and_escaping():
    html = render_doc(doc_mention(5, "x", anchor="v"), lambda ids: {5: "<b>"})
    assert "/r/5/?trecho=v#v" in html and 'data-anchor="v"' in html and "&lt;b&gt;" in html and "<b>" not in html


def test_resolve_called_once_with_all_ids():
    calls = []
    d = {"type": "doc", "content": doc_mention(1, "a")["content"] + doc_mention(2, "b")["content"]
         + doc_mention(1, "a")["content"]}
    render_doc(d, lambda ids: calls.append(sorted(ids)) or {})
    assert calls == [[1, 2]]


def test_render_links_marks_and_unsafe_href_defense():
    html = render_doc(doc_with_link("t", 'https://a.com/?a=1&b="2"'), lambda ids: {})
    assert 'href="https://a.com/?a=1&amp;b=&quot;2&quot;"' in html and "noopener" in html
    # render não confia em validate: href inseguro vira texto simples
    evil = render_doc(doc_with_link("t", "javascript:alert(1)"), lambda ids: {})
    assert "<a" not in evil and "javascript" not in evil and "t" in evil
    marked = {"type": "doc", "content": [{"type": "paragraph", "content": [
        _text("n", [{"type": "bold"}, {"type": "italic"}])]}]}
    out = render_doc(marked, lambda ids: {})
    assert "<strong>" in out and "<em>" in out and ">n<" in out


def test_render_skips_unknown_nodes_without_raw_output():
    d = {"type": "doc", "content": [{"type": "iframe", "content": [_text("<i>")]}, *doc("ok")["content"]]}
    html = render_doc(d, lambda ids: {})
    assert "iframe" not in html and "<i>" not in html and "ok" in html


def test_render_headings_lists_breaks():
    d = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 3, "anchor": "a"}, "content": [_text("T")]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [
            {"type": "paragraph", "content": [_text("1"), {"type": "hardBreak"}, _text("2")]}]}]},
        {"type": "orderedList", "content": [{"type": "listItem", "content": [
            {"type": "paragraph", "content": [_text("o")]}]}]}]}
    html = render_doc(d, lambda ids: {})
    assert '<h3 id="a">T</h3>' in html and "<ul><li>" in html and "<br>" in html and "<ol><li>" in html


def test_render_heading_attrs_are_sanitized():
    bad = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": "<x>", "anchor": 'a"b'},
                                        "content": [_text("A")]}]}
    out = render_doc(bad, lambda ids: {})
    assert "<x>" not in out and 'a"b' not in out


def test_section_stops_at_same_or_higher_heading():
    d = doc_headings([(2, "a", "A"), "x", (3, "b", "B"), "y", (2, "c", "C"), "z"])
    assert plain_text(section(d, "a")) == "A x B y"
    assert plain_text(section(d, "b")) == "B y"
    assert section(d, "nope") is None


def test_section_last_heading_runs_to_end():
    d = doc_headings([(2, "a", "A"), "x", (2, "c", "C"), "z", "w"])
    assert plain_text(section(d, "c")) == "C z w"
    assert section(d, "c")["type"] == "doc"


def test_headings_and_iter_nodes_and_plain_text():
    d = doc_headings([(2, "a", "A"), "x", (3, "b", "B")])
    assert headings(d) == [("a", "A"), ("b", "B")]
    assert [n["type"] for n in iter_nodes(doc("a"))] == ["doc", "paragraph", "text"]
    assert plain_text(doc_mention(1, "Kael")) == "Kael"
    assert plain_text(doc("a", "b")) == "a b"
    assert plain_text({"type": "doc"}) == ""


def test_markdown_output():
    assert doc_to_markdown(doc_headings([(2, "a", "A"), "x"])) == "## A\n\nx\n"


def test_markdown_lists_marks_mentions():
    d = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [_text("a")]}]},
            {"type": "listItem", "content": [{"type": "paragraph", "content": [_text("b")]}]}]},
        {"type": "orderedList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [_text("c")]}]}]},
        {"type": "paragraph", "content": [
            _text("n", [{"type": "bold"}]), _text("i", [{"type": "italic"}]),
            _text("l", [{"type": "link", "attrs": {"href": "https://a.com"}}]),
            {"type": "mention", "attrs": {"record": 1, "anchor": "", "label": "Kael"}}]}]}
    assert doc_to_markdown(d) == "- a\n- b\n\n1. c\n\n**n***i*[l](https://a.com)Kael\n"
    assert doc_to_markdown({"type": "doc"}) == ""


def _colored(color, text="fogo", extra=None):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [
        _text(text, [{"type": "textStyle", "attrs": {"color": color, **(extra or {})}}])]}]}


def _marks(d):
    return d["content"][0]["content"][0].get("marks")


def test_color_mark_is_accepted_and_normalized_to_lowercase():
    assert _marks(validate_doc(_colored("#FF8800"))) == [{"type": "textStyle", "attrs": {"color": "#ff8800"}}]


def test_color_mark_drops_extra_attrs():
    out = validate_doc(_colored("#ff8800", extra={"fontSize": "99px", "x": 1}))
    assert _marks(out) == [{"type": "textStyle", "attrs": {"color": "#ff8800"}}]


@pytest.mark.parametrize("bad", ["red", "url(x)", "#fff", "#ff88001", "#ff8800;x:y", "rgb(1,2,3)", " #ff8800",
                                 "#ff8800\n", "#gg0000", 5, None, ["#ff8800"], {"a": 1}])
def test_hostile_color_is_dropped_but_text_stays(bad):
    out = validate_doc(_colored(bad))
    assert out["content"][0]["content"][0]["text"] == "fogo"
    assert not _marks(out)


def test_color_mark_without_attrs_keeps_text():
    d = {"type": "doc", "content": [{"type": "paragraph", "content": [_text("a", [{"type": "textStyle"}])]}]}
    assert plain_text(validate_doc(d)) == "a"


def test_render_color_with_other_marks():
    marks = [{"type": "bold"}, {"type": "textStyle", "attrs": {"color": "#ff8800"}},
             {"type": "link", "attrs": {"href": "https://a.com"}}]
    d = {"type": "doc", "content": [{"type": "paragraph", "content": [_text("x", marks)]}]}
    out = render_doc(d, lambda ids: {})
    assert '<span style="color:#ff8800">' in out and "<strong>" in out and "<a " in out


@pytest.mark.parametrize("bad", ["red", "#ff8800;x:y", '#ff8800"><script>', "url(x)", 3, None])
def test_render_ignores_invalid_color_in_stored_doc(bad):
    out = render_doc(_colored(bad), lambda ids: {})
    assert "style" not in out and "fogo" in out


def test_color_does_not_leak_into_markdown_search_text_or_editor_doc():
    from content.render import editor_doc
    d = _colored("#ff8800")
    assert doc_to_markdown(d) == "fogo\n"
    assert plain_text(d) == "fogo"
    assert editor_doc(d, lambda ids: {})[0] == d
