import re

import pytest
from playwright.sync_api import expect

from indexing.services import reindex_record
from records.models import Block
from records.services import add_record_tab

from ..helpers import doc_headings, doc_mention
from ..test_indexing import make_record

HEADINGS = doc_headings([(2, "visao", "Visão no Escuro"), "enxerga longe", (2, "fala", "Idioma"), "fala élfico"])


def list_url(record):
    return f"/c/{record.campaign_id}/t/{record.record_type_id}/"


def detail_url(record):
    return f"/r/{record.id}/"


def add_mention(source, target, anchor=""):
    key = source.record_type.fielddef_set.get(kind="long").key
    source.fields[key] = doc_mention(target.id, target.name, anchor)
    source.save()
    reindex_record(source)


def track_url(track):
    return track.fields[track.record_type.fielddef_set.get(kind="link").key]


def in_second_tab(record):
    tab = add_record_tab(record, "Segunda")
    Block.objects.create(tab=tab, kind="text", content=HEADINGS)
    reindex_record(record)
    return tab


def swipe_down(page, selector, distance=300):
    """Toque real, pelo protocolo do navegador: arrasta `selector` para baixo."""
    box = page.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 10
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    for step in range(1, 6):
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchMove", "touchPoints": [{"x": x, "y": y + distance * step / 5}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


@pytest.fixture
def track(campaign):
    record = make_record(campaign, "Trilhas", "Tema de Combate")
    key = record.record_type.fielddef_set.get(kind="link").key
    record.fields[key] = "https://exemplo.com/combate"
    record.save()
    return record


@pytest.fixture
def desktop(page):
    page.set_viewport_size({"width": 1280, "height": 800})


# Passos do plano


def test_panel_opens_and_back_closes_it(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    panel = page.locator("[data-sheet]"); expect(panel).to_be_visible()
    page.go_back(); expect(panel).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_panel_link_opens_target_and_back_returns(page, live_server, logged_in, character, elf):
    add_mention(character, elf); page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.locator("[data-sheet] .mention").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Elfos")
    page.go_back(); expect(page.locator("[data-sheet]")).to_contain_text("Kael")


def test_expand_and_trail(page, live_server, logged_in, character, elf):
    add_mention(character, elf); page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.get_by_role("link", name="Expandir").click()
    page.locator(".mention").first.click()
    page.get_by_role("link", name="Expandir").click()
    expect(page.locator("[data-trail]")).to_contain_text("Kael › Elfos")


def test_track_copy_button(page, context, live_server, logged_in, track):
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(list_url(track)); page.get_by_role("button", name="Copiar link").click()
    assert page.evaluate("navigator.clipboard.readText()") == track_url(track)


# Painel: abrir e fechar


def test_opening_pushes_panel_url_without_reloading(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.evaluate("window.sameDocument = true")
    page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    expect(page).to_have_url(f"{list_url(character)}?painel={character.id}")
    assert page.evaluate("window.sameDocument") is True


def test_opening_keeps_list_group_and_view(page, live_server, logged_in, character):
    url = f"{list_url(character)}?v=galeria"
    page.goto(url); page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    expect(page).to_have_url(f"{url}&painel={character.id}")
    page.go_back()
    expect(page).to_have_url(url)


def test_sheet_appears_before_the_server_answers(page, live_server, logged_in, character):
    page.goto(list_url(character))
    held = []
    page.route("**/painel/*", lambda route: held.append(route))
    page.route("**/painel/", lambda route: held.append(route))
    page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Kael")
    expect(page.locator("[data-sheet]")).not_to_contain_text("Expandir")
    while not held:  # o painel sobe antes de o pedido chegar à rota
        page.wait_for_timeout(20)
    held[0].continue_()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()


def test_closing_before_the_answer_keeps_it_closed(page, live_server, logged_in, character):
    page.goto(list_url(character))
    held = []
    page.route("**/painel/", lambda route: held.append(route))
    page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    page.wait_for_timeout(50)
    if held:
        try:
            held[0].continue_()
        except Exception:
            pass  # o pedido já foi cancelado, que é o esperado
    page.wait_for_timeout(200)
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_failed_load_says_so_and_can_be_closed(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.route("**/painel/", lambda route: route.fulfill(status=500, body="erro"))
    page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Não foi possível abrir")
    page.locator("[data-sheet-close]").click()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_expired_session_goes_to_login_instead_of_filling_the_panel(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.context.clear_cookies()
    page.get_by_text("Kael").click()
    expect(page.locator("input[type=password]")).to_be_visible()
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_escape_while_typing_does_not_close_the_panel(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    page.locator("[data-list-filter] input").focus()
    page.keyboard.press("Escape")
    expect(page.locator("[data-sheet]")).to_be_visible()


def test_back_to_previous_panel_needs_no_request(page, live_server, logged_in, character, elf):
    add_mention(character, elf); page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.locator("[data-sheet] .mention").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Elfos")
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.go_back()
    expect(page.locator("[data-sheet]")).to_contain_text("Kael")
    assert requests == []


def test_close_button_dismisses_without_navigating(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.evaluate("window.sameDocument = true")
    page.get_by_text("Kael").click()
    page.locator("[data-sheet-close]").click()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))
    assert page.evaluate("window.sameDocument") is True


def test_close_button_dismisses_a_stack_of_panels(page, live_server, logged_in, character, elf):
    add_mention(character, elf); page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.locator("[data-sheet] .mention").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Elfos")
    page.locator("[data-sheet-close]").click()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_row_tapped_with_panel_open_swaps_without_stacking(page, live_server, logged_in, campaign, character):
    other = make_record(campaign, "Personagens", "Mira")
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Kael")
    page.locator(f'[data-panel-url="/r/{other.id}/painel/"]').click()
    expect(page.locator("[data-sheet]")).to_contain_text("Mira")
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_escape_closes(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_direct_url_opens_panel_and_back_closes_it_inside_the_site(page, live_server, logged_in, character):
    url = f"{list_url(character)}?painel={character.id}"
    page.goto(url)
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_close_button_on_direct_url(page, live_server, logged_in, character):
    page.goto(f"{list_url(character)}?painel={character.id}")
    page.locator("[data-sheet-close]").click()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_reload_keeps_panel_and_back_still_closes(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.reload()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.go_back()
    expect(page).to_have_url(list_url(character))
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_back_from_expand_returns_to_open_panel(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.get_by_role("link", name="Expandir").click()
    expect(page).to_have_url(detail_url(character))
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_ctrl_click_on_row_is_left_to_the_browser(page, live_server, logged_in, character):
    page.goto(list_url(character))
    with page.context.expect_page() as popup:
        page.get_by_text("Kael").click(modifiers=["Control"])
    assert popup.value.url.endswith(detail_url(character))
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_sheet_causes_no_horizontal_scroll(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# Arrastar


def test_drag_down_closes_and_uses_history(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    swipe_down(page, "[data-sheet]")
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_short_drag_keeps_the_panel_in_place(page, live_server, logged_in, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    before = page.locator("[data-sheet]").bounding_box()
    page.wait_for_timeout(300)
    swipe_down(page, "[data-sheet]", distance=30)
    page.wait_for_timeout(300)
    expect(page.locator("[data-sheet]")).to_be_visible()
    assert page.locator("[data-sheet]").bounding_box()["y"] == pytest.approx(before["y"], abs=2)


def test_drag_on_scrolled_content_scrolls_instead_of_closing(page, live_server, logged_in, character):
    key = character.record_type.fielddef_set.get(kind="long").key
    character.fields[key] = doc_headings(*[f"Título {n}" for n in range(30)])
    character.save()
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_attached()
    page.locator("[data-sheet]").evaluate("el => { el.scrollTop = 200; }")
    swipe_down(page, "[data-sheet]")
    page.wait_for_timeout(300)
    expect(page.locator("[data-sheet]")).to_be_visible()
    expect(page).to_have_url(f"{list_url(character)}?painel={character.id}")


# Computador


def test_desktop_panel_sits_beside_the_list(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    panel = page.locator("[data-sheet]")
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    box, row = panel.bounding_box(), page.get_by_role("link", name="Kael").first.bounding_box()
    assert box["height"] > 500
    assert row["x"] + row["width"] <= box["x"]
    assert box["x"] + box["width"] == pytest.approx(1280, abs=1)


def test_panel_is_a_bottom_sheet_just_below_900px(page, live_server, logged_in, character):
    page.set_viewport_size({"width": 899, "height": 700})
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    box = page.locator("[data-sheet]").bounding_box()
    assert box["x"] == 0 and box["width"] == 899


def test_side_panel_starts_at_exactly_900px(page, live_server, logged_in, character):
    page.set_viewport_size({"width": 900, "height": 700})
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    box = page.locator("[data-sheet]").bounding_box()
    assert box["x"] > 0 and box["x"] + box["width"] == pytest.approx(900, abs=1)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# Âncoras


def test_anchor_link_opens_other_tab_at_the_passage(page, live_server, logged_in, character, elf):
    in_second_tab(elf)
    add_mention(character, elf, "visao")
    page.goto(detail_url(character))
    page.locator("[data-editor=field] .mention").click()
    expect(page).to_have_url(re.compile(rf"/r/{elf.id}/\?trecho=visao#visao$"))
    expect(page.locator("#visao")).to_be_in_viewport()
    expect(page.locator(".strip a.on").first).to_have_text("Segunda")


def test_bare_hash_link_also_reaches_other_tab(page, live_server, logged_in, elf):
    in_second_tab(elf)
    page.goto(f"{detail_url(elf)}#visao")
    expect(page.locator("#visao")).to_be_in_viewport()
    expect(page.locator(".strip a.on").first).to_have_text("Segunda")


def test_bare_hash_to_unknown_heading_does_not_loop(page, live_server, logged_in, elf):
    page.goto(f"{detail_url(elf)}#nada")
    page.wait_for_timeout(300)
    expect(page).to_have_url(re.compile(r"#nada$"))
    expect(page.locator("h1")).to_have_text("Elfos")


def test_panel_mention_to_heading_shows_only_that_section(page, live_server, logged_in, character, elf):
    in_second_tab(elf)
    add_mention(character, elf, "visao")
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.locator("[data-sheet] .mention").click()
    sheet = page.locator("[data-sheet]")
    expect(sheet).to_contain_text("enxerga longe")
    expect(sheet).not_to_contain_text("fala élfico")
    expect(page).to_have_url(f"{list_url(character)}?painel={elf.id}&ancora=visao")
    page.get_by_role("link", name="Expandir").click()
    expect(page.locator("#visao")).to_be_in_viewport()


def test_full_screen_with_panel_keeps_its_own_passage(page, live_server, logged_in, character, elf):
    in_second_tab(character)
    add_mention(character, elf)
    page.goto(f"{detail_url(character)}?trecho=visao#visao")
    page.locator("[data-editor=field] .mention").click()
    expect(page.locator("[data-sheet]")).to_contain_text("Elfos")
    page.reload()
    expect(page.locator("[data-sheet]")).to_be_visible()
    expect(page.locator(".strip a.on").first).to_have_text("Segunda")


# Caminho


def test_trail_cuts_when_returning_to_an_item(page, live_server, logged_in, campaign, character, elf):
    vision = make_record(campaign, "Raças", "Visão")
    page.goto(detail_url(character)); page.goto(detail_url(elf)); page.goto(detail_url(vision))
    expect(page.locator("[data-trail]")).to_contain_text("Kael › Elfos › Visão")
    page.goto(detail_url(elf))
    expect(page.locator("[data-trail]")).to_contain_text("Kael › Elfos")
    expect(page.locator("[data-trail]")).not_to_contain_text("Visão")


def test_trail_shows_three_levels_with_abbreviated_start(page, live_server, logged_in, campaign):
    records = [make_record(campaign, "Raças", name) for name in ("Um", "Dois", "Tres", "Quatro")]
    for record in records:
        page.goto(detail_url(record))
    expect(page.locator("[data-trail]")).to_have_text("… › Dois › Tres › Quatro")
    expect(page.locator("[data-trail] a", has_text="Dois")).to_have_attribute("href", detail_url(records[1]))


def test_trail_follows_panels_and_their_dismissal(page, live_server, logged_in, character, elf):
    add_mention(character, elf); page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.locator("[data-trail]")).to_contain_text("Personagens › Kael")
    page.locator("[data-sheet] .mention").click()
    expect(page.locator("[data-trail]")).to_contain_text("Kael › Elfos")
    page.go_back()
    expect(page.locator("[data-trail]")).not_to_contain_text("Elfos")
    page.go_back()
    expect(page.locator("[data-trail]")).not_to_contain_text("Kael")


def test_trail_names_the_heading_reached(page, live_server, logged_in, character, elf):
    in_second_tab(elf)
    add_mention(character, elf, "visao")
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    page.locator("[data-sheet] .mention").click()
    expect(page.locator("[data-trail]")).to_contain_text("Kael › Elfos › Visão no Escuro")


def test_trail_belongs_to_the_campaign(page, live_server, logged_in, user, make_campaign, character):
    other = make_record(make_campaign(user, "Outra"), "Personagens", "Distante")
    page.goto(detail_url(character)); page.goto(detail_url(other))
    expect(page.locator("[data-trail]")).not_to_contain_text("Kael")


def test_trail_is_separate_per_browser_tab(page, context, live_server, logged_in, character, elf):
    page.goto(detail_url(character))
    second = context.new_page()
    second.goto(detail_url(elf))
    expect(second.locator("[data-trail]")).not_to_contain_text("Kael")


def test_trail_survives_blocked_session_storage(page, live_server, logged_in, character):
    page.add_init_script(
        "Object.defineProperty(window, 'sessionStorage', {get() { throw new Error('bloqueado'); }})")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(list_url(character)); page.get_by_text("Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    assert errors == []


# Cópia


def test_copy_shows_feedback_and_restores_label(page, context, live_server, logged_in, track):
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(list_url(track))
    button = page.get_by_role("button", name="Copiar link")
    button.click()
    expect(page.locator("[data-copy]")).to_have_text("Copiado")
    expect(page.locator("[data-copy]")).to_have_text("Copiar link", timeout=4000)


def test_copy_falls_back_to_textarea(page, context, live_server, logged_in, track):
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.add_init_script("""
        const real = navigator.clipboard;
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: () => Promise.reject(new Error("recusado")),
            readText: () => real.readText(),
        }});
    """)
    page.goto(list_url(track))
    page.get_by_role("button", name="Copiar link").click()
    expect(page.locator("[data-copy]")).to_have_text("Copiado")
    assert page.evaluate("navigator.clipboard.readText()") == track_url(track)
    expect(page.locator("textarea")).to_have_count(0)


def test_copy_does_not_open_the_panel(page, context, live_server, logged_in, track):
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(list_url(track))
    page.get_by_role("button", name="Copiar link").click()
    expect(page.locator("[data-copy]")).to_have_text("Copiado")
    expect(page.locator("[data-sheet]")).to_be_hidden()


# Busca


def test_search_stays_quiet_on_mobile_and_opens_on_tap(page, live_server, logged_in, character):
    page.goto(detail_url(character))
    field = page.locator("[data-search-input]")
    expect(field).to_be_hidden()
    toggle = page.get_by_role("button", name="Buscar")
    box = toggle.bounding_box()
    assert box["width"] >= 44 and box["height"] >= 44
    toggle.click()
    expect(field).to_be_focused()
    field.fill("kael")
    expect(page.locator("#results")).to_contain_text("Kael")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_search_collapses_on_escape_and_outside_tap(page, live_server, logged_in, character):
    page.goto(detail_url(character))
    page.get_by_role("button", name="Buscar").click()
    page.keyboard.press("Escape")
    expect(page.locator("[data-search-input]")).to_be_hidden()
    page.get_by_role("button", name="Buscar").click()
    page.mouse.click(195, 700)
    expect(page.locator("[data-search-input]")).to_be_hidden()


def test_search_input_uses_16px_font(page, live_server, logged_in, character):
    page.goto(detail_url(character))
    page.get_by_role("button", name="Buscar").click()
    assert page.locator("[data-search-input]").evaluate("el => getComputedStyle(el).fontSize") == "16px"


def test_ctrl_k_focuses_search_on_any_desktop_screen(page, live_server, logged_in, desktop, character):
    for url in (detail_url(character), list_url(character), f"/c/{character.campaign_id}/"):
        page.goto(url)
        page.keyboard.press("Control+k")
        expect(page.locator("[data-search-input]")).to_be_focused()


def test_ctrl_k_works_from_inside_the_editor(page, live_server, logged_in, desktop, character):
    page.goto(detail_url(character))
    page.locator("[data-editor=text] [contenteditable]").click()
    page.keyboard.press("Control+k")
    expect(page.locator("[data-search-input]")).to_be_focused()


def test_desktop_search_is_visible_without_toggle(page, live_server, logged_in, desktop, character):
    page.goto(detail_url(character))
    expect(page.locator("[data-search-input]")).to_be_visible()
    expect(page.get_by_role("button", name="Buscar")).to_be_hidden()


def test_search_result_can_be_followed(page, live_server, logged_in, desktop, character):
    page.goto(detail_url(character))
    page.keyboard.press("Control+k")
    page.keyboard.type("kael")
    page.locator("#results a").first.click()
    expect(page).to_have_url(detail_url(character))


# Filtro da lista


def test_list_filter_narrows_rows_ignoring_accents(page, live_server, logged_in, campaign, character):
    make_record(campaign, "Personagens", "Érica")
    page.goto(list_url(character))
    page.locator("[data-list-filter] input").fill("eri")
    expect(page.get_by_role("link", name="Érica")).to_be_visible()
    expect(page.get_by_role("link", name="Kael")).to_be_hidden()


def test_list_filter_says_when_nothing_matches(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.locator("[data-list-filter] input").fill("zzz")
    expect(page.get_by_text("Nada encontrado.")).to_be_visible()
    page.locator("[data-list-filter] input").fill("")
    expect(page.get_by_role("link", name="Kael")).to_be_visible()
    expect(page.get_by_text("Nada encontrado.")).to_be_hidden()


def test_list_filter_works_in_gallery(page, live_server, logged_in, campaign, character):
    make_record(campaign, "Personagens", "Mira")
    page.goto(f"{list_url(character)}?v=galeria")
    page.locator("[data-list-filter] input").fill("mir")
    expect(page.get_by_role("link", name="Mira")).to_be_visible()
    expect(page.get_by_role("link", name="Kael")).to_be_hidden()


def test_list_filter_does_not_reload_on_enter(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.evaluate("window.sameDocument = true")
    box = page.locator("[data-list-filter] input")
    box.fill("kael")
    box.press("Enter")
    assert page.evaluate("window.sameDocument") is True
    expect(page).to_have_url(list_url(character))


def test_list_filter_survives_opening_and_closing_the_panel(page, live_server, logged_in, campaign, character):
    make_record(campaign, "Personagens", "Mira")
    page.goto(list_url(character))
    page.locator("[data-list-filter] input").fill("kael")
    page.get_by_role("link", name="Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.go_back()
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page.get_by_role("link", name="Mira")).to_be_hidden()
    expect(page.locator("[data-list-filter] input")).to_have_value("kael")
