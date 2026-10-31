import re

import pytest
from playwright.sync_api import expect

from content.doc import headings, iter_nodes, validate_doc
from indexing.services import reindex_record
from records.models import Block
from records.save import add_embed, rename_record

from ..helpers import doc, doc_headings, doc_mention
from ..test_indexing import make_record, set_body

TEXT = "[data-editor=text] [contenteditable]"
FIELD = "[data-editor=field] [contenteditable]"

# Trecho como o Google Docs põe na área de transferência.
GOOGLE_DOCS = (
    '<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1a2b">'
    '<h1 dir="ltr" id="h.title"><span style="font-weight:400;">Capítulo</span></h1>'
    '<h2 dir="ltr" id="h.abc"><span style="font-weight:400;">Origem</span></h2>'
    '<h4 dir="ltr"><span style="font-weight:400;">Detalhe</span></h4>'
    '<p dir="ltr"><span style="font-weight:700;">forte</span><span> e </span>'
    '<span style="font-style:italic;">leve</span> '
    '<a href="tel:+5511"><span>ligar</span></a> <a href="/relativo"><span>aqui</span></a> '
    '<a href="https://exemplo.com/x"><span>site</span></a></p>'
    '<ul><li dir="ltr"><p dir="ltr" role="presentation"><span>um</span></p></li>'
    '<ul><li dir="ltr"><p dir="ltr" role="presentation"><span>dentro</span></p></li></ul>'
    '<li dir="ltr"><p dir="ltr" role="presentation"><span>dois</span></p></li></ul>'
    '<ol><li dir="ltr"><p dir="ltr" role="presentation"><span>primeiro</span></p></li></ol>'
    '<table><tr><td><span>célula</span></td></tr></table>'
    '<hr><img src="https://exemplo.com/a.png"></b>'
)


def url_of(record):
    return f"/r/{record.id}/"


def paste(page, selector, html):
    page.locator(selector).first.evaluate(
        """(el, html) => {
            const data = new DataTransfer();
            data.setData("text/html", html);
            el.dispatchEvent(new ClipboardEvent("paste", {clipboardData: data, bubbles: true, cancelable: true}));
        }""", html)


def saved(page, trigger, content=""):
    """Roda `trigger` e espera o envio que traz `content`, um trecho do corpo ou uma função sobre ele.

    Esperar a resposta, e não consultar o banco em laço: no SQLite em memória o teste
    e o servidor dividem a conexão, e ler durante uma escrita dá "table is locked".
    """
    matches = content if callable(content) else lambda body: content in body

    def is_it(response):
        body = response.request.post_data or ""
        return ("/blocos/" in response.url or "/campos/" in response.url) and bool(body) and matches(body)

    with page.expect_response(is_it) as info:
        trigger()
    assert info.value.status == 200, info.value.text()
    return info.value


def block_of(record):
    return Block.objects.filter(tab__record=record, kind="text").order_by("position", "id").first()


def texts(block):
    return [n["text"] for n in iter_nodes(block.content) if n["type"] == "text"]


def test_at_mention_inserts_link(page, live_server, logged_in, character, elf):
    page.goto(url_of(character)); page.locator("[data-editor] [contenteditable]").first.click()
    page.keyboard.type("Primo de @elf")
    page.get_by_role("option", name="Elfos").click()
    expect(page.locator("[data-editor] .mention")).to_have_text("Elfos")


def test_suggestions_are_a_listbox_and_work_by_keyboard(page, live_server, logged_in, character, elf, campaign):
    make_record(campaign, "Raças", "Elfos Negros")
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.type(" @elf")
    listbox = page.get_by_role("listbox")
    expect(listbox.get_by_role("option")).to_have_count(2)
    page.keyboard.press("ArrowDown"); page.keyboard.press("Enter")
    expect(listbox).to_have_count(0)
    expect(page.locator(TEXT).locator(".mention")).to_have_text("Elfos Negros")


def test_mention_survives_save_and_reload_with_its_attrs(page, live_server, logged_in, character, elf):
    set_body(elf, doc_headings([(2, "visao", "Visão no Escuro"), "enxerga"]))
    reindex_record(elf)
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.type(" @visao")
    saved(page, page.get_by_role("option", name="Elfos › Visão no Escuro").click, '"mention"')

    mention = next(n for n in iter_nodes(block_of(character).content) if n["type"] == "mention")
    assert mention["attrs"] == {"record": elf.id, "anchor": "visao", "label": "Elfos › Visão no Escuro"}

    page.reload()
    link = page.locator(TEXT).locator(".mention")
    expect(link).to_have_text("Elfos › Visão no Escuro")
    expect(link).to_have_attribute("href", f"/r/{elf.id}/#visao")
    link.click()
    expect(page).to_have_url(re.compile(rf"/r/{elf.id}/#visao$"))
    expect(page.locator("#visao")).to_be_in_viewport()


def test_mention_shows_current_name_and_deleted_target_is_struck(page, live_server, logged_in, character, elf, campaign):
    orc = make_record(campaign, "Raças", "Orcs")
    content = doc_mention(elf.id, "Elfos")
    content["content"][0]["content"].append(doc_mention(orc.id, "Orcs")["content"][0]["content"][0])
    set_body(character, content)
    rename_record(elf, "Elfos Altos")
    orc.delete()
    page.goto(url_of(character))
    mentions = page.locator(TEXT).locator(".mention")
    expect(mentions.nth(0)).to_have_text("Elfos Altos")
    expect(page.locator(TEXT).locator("s.mention")).to_have_text("Orcs")


def test_editor_keeps_text_from_the_doc_and_saves_with_the_version(page, live_server, logged_in, character):
    page.goto(url_of(character))
    expect(page.locator(TEXT)).to_have_text("texto")
    page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.type(" mais")
    saved(page, lambda: page.keyboard.type("!"), "texto mais!")
    assert texts(block_of(character)) == ["texto mais!"]
    assert block_of(character).version >= 2
    expect(page.get_by_role("button", name="Remover bloco")).to_be_visible()
    assert page.locator("[data-editor] form").count() == 0


def test_change_event_carries_the_doc(page, live_server, logged_in, character):
    page.goto(url_of(character))
    page.evaluate("""() => {
        window.lastDoc = null;
        document.addEventListener("editor:change", e => { window.lastDoc = e.detail.doc; });
    }""")
    page.locator(TEXT).click(); page.keyboard.type("x")
    page.wait_for_function("window.lastDoc !== null")
    assert page.evaluate("window.lastDoc.type") == "doc"


def test_new_heading_gets_anchor(page, live_server, logged_in, character):
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.press("Enter")
    page.get_by_role("button", name="Título", exact=True).click()
    saved(page, lambda: page.keyboard.type("Origem"), "Origem")
    ((anchor, text),) = headings(block_of(character).content)
    assert text == "Origem" and re.fullmatch(r"h-[0-9a-f]{8}", anchor)


def test_changing_heading_level_keeps_its_anchor(page, live_server, logged_in, character):
    set_body(character, doc_headings([(2, "origem", "Origem")]))
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.get_by_role("button", name="Subtítulo").click()
    expect(page.locator(TEXT).locator("h3")).to_have_text("Origem")
    saved(page, lambda: page.keyboard.type("!"), "!")
    node = next(n for n in iter_nodes(block_of(character).content) if n["type"] == "heading")
    assert node["attrs"] == {"level": 3, "anchor": "origem"}


def test_pasted_duplicate_heading_gets_new_anchor_and_original_keeps_it(page, live_server, logged_in, character):
    content = doc_headings([(2, "origem", "Origem"), "corpo"])
    content["content"].insert(0, {"type": "paragraph"})
    set_body(character, content)
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+Home")
    saved(page, lambda: paste(page, TEXT, '<h2 id="origem">Cópia</h2>'), "Cópia")
    found = headings(block_of(character).content)
    assert [t for _, t in found] == ["Cópia", "Origem"] and len({a for a, _ in found}) == 2
    assert dict((t, a) for a, t in found)["Origem"] == "origem"


def test_splitting_a_heading_regenerates_the_second_anchor(page, live_server, logged_in, character):
    set_body(character, doc_headings([(2, "origem", "Origem Antiga")]))
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End")
    for _ in range(6):
        page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(300)  # o editor lê a seleção no selectionchange, depois da tecla
    saved(page, lambda: page.keyboard.press("Enter"), lambda body: body.count('"heading"') == 2)
    first, second = headings(block_of(character).content)
    assert first[0] == "origem" and second[0] != "origem"


def test_opening_a_text_does_not_save_it(page, live_server, logged_in, character):
    set_body(character, doc_headings([(2, "origem", "Origem")]))
    page.goto(url_of(character))
    expect(page.locator(TEXT).locator("h2")).to_have_text("Origem")
    page.wait_for_timeout(1200)
    assert block_of(character).version == 1


def test_suggestions_close_when_leaving_the_text(page, live_server, logged_in, character, elf):
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.type(" @elf")
    listbox = page.get_by_role("listbox")
    expect(listbox).to_be_visible()
    page.locator("h1").click()
    expect(listbox).to_have_count(0)


def test_google_docs_paste_keeps_structure_and_is_accepted(page, live_server, logged_in, character):
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.press("Enter")
    saved(page, lambda: paste(page, TEXT, GOOGLE_DOCS), "Origem")
    content = block_of(character).content
    assert validate_doc(content) == content
    nodes = list(iter_nodes(content))
    assert [(n["attrs"]["level"], n["content"][0]["text"]) for n in nodes if n["type"] == "heading"] == [
        (2, "Capítulo"), (2, "Origem"), (3, "Detalhe")]
    marks = {n["text"]: [m["type"] for m in n.get("marks", [])] for n in nodes if n["type"] == "text"}
    assert marks["forte"] == ["bold"] and marks["leve"] == ["italic"]
    assert marks["Capítulo"] == [] and marks["site"] == ["link"]
    hrefs = [m["attrs"]["href"] for n in nodes for m in n.get("marks", []) if m["type"] == "link"]
    assert hrefs == ["https://exemplo.com/x"]
    assert any("ligar" in t and "aqui" in t for t in marks)
    kinds = {n["type"] for n in nodes}
    assert {"bulletList", "orderedList", "listItem"} <= kinds
    assert len(content["content"]) >= 5
    assert "dentro" in marks and "célula" in marks


def test_toolbar_marks_bold_and_italic(page, live_server, logged_in, character):
    set_body(character, doc(""))
    page.goto(url_of(character))
    toolbar = page.get_by_role("toolbar", name="Formatação")
    expect(toolbar).to_be_hidden()
    page.locator(TEXT).click()
    expect(toolbar).to_be_visible()
    box = toolbar.get_by_role("button", name="Negrito").bounding_box()
    assert box["height"] >= 44 and box["width"] >= 44
    toolbar.get_by_role("button", name="Negrito").click()
    expect(toolbar.get_by_role("button", name="Negrito")).to_have_attribute("aria-pressed", "true")
    saved(page, lambda: page.keyboard.type("duro"), "duro")
    assert block_of(character).content["content"][0]["content"][0]["marks"] == [{"type": "bold"}]


def test_toolbar_stays_above_the_phone_keyboard(page, live_server, logged_in, character):
    page.add_init_script("""
        const fake = new EventTarget();
        fake.height = window.innerHeight; fake.offsetTop = 0;
        Object.defineProperty(window, "visualViewport", {value: fake});
        window.fakeKeyboard = px => { fake.height = window.innerHeight - px; fake.dispatchEvent(new Event("resize")); };
    """)
    page.goto(url_of(character)); page.locator(TEXT).click()
    toolbar = page.get_by_role("toolbar", name="Formatação")
    expect(toolbar).to_be_visible()
    box = toolbar.bounding_box()
    assert box["y"] + box["height"] == pytest.approx(844, abs=1)
    page.evaluate("fakeKeyboard(300)")
    page.wait_for_function("""() => {
        const r = document.querySelector("[role=toolbar]").getBoundingClientRect();
        return Math.abs(r.bottom - 544) <= 1;
    }""")


def test_editor_activates_after_htmx_swap(page, live_server, logged_in, character):
    page.goto(url_of(character))
    page.evaluate("""() => {
        const box = document.createElement("div");
        box.innerHTML = '<div data-editor="text" data-doc="swap-doc" data-suggest-url="/x"></div>'
            + '<script type="application/json" id="swap-doc">{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"trocado"}]}]}<\\/script>';
        document.querySelector("main").append(box);
        box.dispatchEvent(new CustomEvent("htmx:afterSwap", {bubbles: true, detail: {target: box}}));
    }""")
    expect(page.locator("main [contenteditable]", has_text="trocado")).to_have_count(1)
    # Reativar não pode montar um segundo editor no mesmo elemento.
    page.evaluate("""() => document.body.dispatchEvent(
        new CustomEvent("htmx:afterSwap", {bubbles: true, detail: {target: document.body}}))""")
    expect(page.locator("main [contenteditable]", has_text="trocado")).to_have_count(1)


def test_record_screen_shows_basic_fields(page, live_server, logged_in, character):
    defs = {f.label: f for f in character.record_type.fielddef_set.all()}
    character.fields = {defs["Ocupação"].key: "Ladino", defs["Idade"].key: "34", defs["Resumo"].key: doc("meio-elfo")}
    character.save()
    page.goto(url_of(character))
    expect(page.get_by_label("Ocupação")).to_have_value("Ladino")
    expect(page.get_by_label("Idade")).to_have_value("34")
    expect(page.locator(FIELD)).to_have_text("meio-elfo")


def test_long_field_saves_by_key_and_version(page, live_server, logged_in, character):
    key = character.record_type.fielddef_set.get(kind="long").key
    character.fields = {key: doc("antigo")}
    character.field_versions = {key: 4}
    character.save()
    page.goto(url_of(character)); page.locator(FIELD).click()
    page.keyboard.press("Control+End")
    assert saved(page, lambda: page.keyboard.type("!")).json()["version"] == 5
    assert saved(page, lambda: page.keyboard.type("?")).json()["version"] == 6
    character.refresh_from_db()
    assert character.fields[key] == doc("antigo!?")


def test_long_field_with_old_plain_text_opens_in_the_editor(page, live_server, logged_in, character):
    key = character.record_type.fielddef_set.get(kind="long").key
    character.fields = {key: "texto antigo"}
    character.save()
    page.goto(url_of(character))
    expect(page.locator(FIELD)).to_have_text("texto antigo")


def test_empty_tab_lets_you_write_right_away(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    assert not Block.objects.filter(tab__record=empty).exists()
    page.goto(url_of(empty))
    assert not Block.objects.filter(tab__record=empty).exists()
    expect(page.get_by_role("button", name="+ Texto")).to_have_count(0)
    page.locator(TEXT).click()
    saved(page, lambda: page.keyboard.type("direto"), "direto")
    saved(page, lambda: page.keyboard.type("!"), "direto!")
    assert block_of(empty).content == doc("direto!")
    assert Block.objects.filter(tab__record=empty).count() == 1
    page.reload()
    expect(page.locator(TEXT)).to_have_text("direto!")


def test_embed_picker_adds_a_record(page, live_server, logged_in, character, elf):
    page.goto(url_of(character))
    page.get_by_text("Incorporar").click()
    page.get_by_role("combobox", name="Origem").fill("elf")
    page.get_by_role("option", name="Elfos").click()
    expect(page.locator(".embed-block")).to_contain_text("base")
    assert Block.objects.get(kind="embed").embed_record == elf


def test_embed_picker_adds_a_heading(page, live_server, logged_in, character, elf):
    set_body(elf, doc_headings([(2, "v", "Visão"), "enxerga", (2, "g", "Graça"), "dança"]))
    reindex_record(elf)
    page.goto(url_of(character))
    page.get_by_text("Incorporar").click()
    page.get_by_role("combobox", name="Origem").fill("graça")
    page.get_by_role("option", name="Elfos › Graça").click()
    expect(page.locator(".embed-block")).to_contain_text("dança")
    expect(page.locator(".embed-block")).not_to_contain_text("enxerga")
    block = Block.objects.get(kind="embed")
    assert (block.embed_record, block.embed_anchor) == (elf, "g")


def test_embed_picker_does_not_offer_the_record_itself(page, live_server, logged_in, character, elf):
    add_embed(character.tab_set.first(), elf, "")
    page.goto(url_of(character))
    page.get_by_text("Incorporar").click()
    page.get_by_role("combobox", name="Origem").fill("kael")
    expect(page.get_by_text("Nada encontrado")).to_be_visible()
    expect(page.get_by_role("option")).to_have_count(0)


SUGGEST = re.compile(r"/sugestoes/\?q=")
BURST = "elfos negros antigos"


def suggest_queries(page):
    """Lista viva dos pedidos de sugestão feitos pela página."""
    urls = []
    page.on("request", lambda r: urls.append(r.url) if SUGGEST.search(r.url) else None)
    return urls


def watch_no_results(page):
    page.evaluate("""() => {
        window.sawNoResults = false;
        new MutationObserver(() => {
            const list = document.querySelector("[role=listbox]");
            if (list && !list.hidden && list.textContent.includes("Nada encontrado")) window.sawNoResults = true;
        }).observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true});
    }""")


def test_typing_a_burst_sends_one_suggest_request(page, live_server, logged_in, character, campaign):
    make_record(campaign, "Raças", "Elfos Negros Antigos")
    urls = suggest_queries(page)
    page.goto(url_of(character)); page.locator(TEXT).click()
    page.keyboard.press("Control+End"); page.keyboard.type(f" @{BURST}", delay=15)
    expect(page.get_by_role("option", name="Elfos Negros Antigos")).to_be_visible()
    assert 1 <= len(urls) <= 2, urls
    assert urls[-1].endswith("q=elfos%20negros%20antigos")


def test_picker_burst_sends_one_suggest_request(page, live_server, logged_in, character, campaign):
    make_record(campaign, "Raças", "Elfos Negros Antigos")
    urls = suggest_queries(page)
    page.goto(url_of(character))
    page.get_by_text("Incorporar").click()
    page.get_by_role("combobox", name="Origem").press_sequentially(BURST, delay=15)
    expect(page.get_by_role("option", name="Elfos Negros Antigos")).to_be_visible()
    assert 1 <= len(urls) <= 2, urls


def test_slow_suggest_shows_searching_and_enter_waits(page, live_server, logged_in, character, elf):
    held = []
    page.route(SUGGEST, lambda route: held.append(route))
    page.goto(url_of(character)); page.locator(TEXT).click()
    watch_no_results(page)
    page.keyboard.press("Control+End"); page.keyboard.type(" @elf")
    listbox = page.get_by_role("listbox")
    expect(listbox).to_contain_text("Buscando")
    page.wait_for_timeout(400)
    assert held, "o pedido deveria estar segurado"

    page.keyboard.press("Enter")
    expect(page.locator(TEXT).locator("p")).to_have_count(1)
    assert page.evaluate("window.sawNoResults") is False

    held[-1].continue_()
    expect(page.get_by_role("option", name="Elfos")).to_be_visible()
    assert page.evaluate("window.sawNoResults") is False


def test_slow_suggest_keeps_the_list_and_enter_picks_only_after_the_answer(page, live_server, logged_in, character, elf):
    held = []
    page.route(SUGGEST, lambda route: held.append(route))
    page.goto(url_of(character)); page.locator(TEXT).click()
    watch_no_results(page)
    page.keyboard.press("Control+End"); page.keyboard.type(" @elf")
    page.wait_for_timeout(400)
    held[-1].continue_()
    option = page.get_by_role("option", name="Elfos")
    expect(option).to_be_visible()

    answered = len(held)
    page.keyboard.type("o")
    expect(option).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator(TEXT).locator("p")).to_have_count(1)
    expect(page.locator(TEXT).locator(".mention")).to_have_count(0)
    page.wait_for_timeout(400)
    assert len(held) > answered and page.evaluate("window.sawNoResults") is False

    held[-1].continue_()
    expect(option).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator(TEXT).locator(".mention")).to_have_text("Elfos")


def test_picker_enter_waits_for_the_answer(page, live_server, logged_in, character, elf):
    held = []
    page.route(SUGGEST, lambda route: held.append(route))
    page.goto(url_of(character))
    page.get_by_text("Incorporar").click()
    box = page.get_by_role("combobox", name="Origem")
    box.press_sequentially("elf")
    expect(page.get_by_role("listbox")).to_contain_text("Buscando")
    box.press("Enter")
    assert not Block.objects.filter(kind="embed").exists()
    page.wait_for_timeout(400)
    held[-1].continue_()
    expect(page.get_by_role("option", name="Elfos")).to_be_visible()


def test_no_horizontal_scroll_with_editor(page, live_server, logged_in, character):
    page.goto(url_of(character)); page.locator(TEXT).click()
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
