import io

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from playwright.sync_api import expect

from assets.storage import store_upload
from campaigns.models import Campaign, FieldDef, ListGroup, RecordType
from records.models import Block, Record, Tab
from records.services import add_record_tab

from ..helpers import doc
from ..test_indexing import make_record


def list_url(record):
    return f"/c/{record.campaign_id}/t/{record.record_type_id}/"


def template_url(record):
    return f"{list_url(record)}modelo/"


@pytest.fixture
def desktop(page):
    page.set_viewport_size({"width": 1280, "height": 800})


def menu(page):
    return page.get_by_role("menuitem", name="Deletar")


def delete_by_menu(page, target):
    target.click(button="right")
    menu(page).click()


def long_press(page, locator, hold_ms=650, move=None):
    """Toque real, pelo protocolo do navegador: segura sobre `locator` e solta."""
    box = locator.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    if move:
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y + move}]})
    page.wait_for_timeout(hold_ms)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def small_png(name="a.png"):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 200, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), "image/png")


# Menu


def test_right_click_deletes_a_record_without_reloading(page, live_server, logged_in, desktop, campaign, character):
    other = make_record(campaign, "Personagens", "Mira")
    page.goto(list_url(character))
    page.evaluate("window.sameDocument = true")
    delete_by_menu(page, page.get_by_role("link", name="Kael"))
    expect(page.get_by_role("link", name="Kael")).to_have_count(0)
    expect(page.get_by_role("link", name="Mira")).to_be_visible()
    assert page.evaluate("window.sameDocument") is True
    assert list(Record.objects.filter(campaign=campaign)) == [other]


def test_right_click_deletes_a_campaign(page, live_server, logged_in, desktop, campaign):
    page.goto("/c/")
    delete_by_menu(page, page.get_by_role("link", name="Vael"))
    expect(page.get_by_role("link", name="Vael")).to_have_count(0)
    assert not Campaign.objects.filter(pk=campaign.pk).exists()


def test_right_click_deletes_a_type_from_a_screen_without_forms(page, live_server, logged_in, desktop, campaign, character):
    page.goto(f"/c/{campaign.id}/")
    delete_by_menu(page, page.locator(".type-row", has_text="Personagens").locator(".type-link"))
    expect(page.locator(".type-row", has_text="Personagens")).to_have_count(0)
    assert not RecordType.objects.filter(campaign=campaign, name="Personagens").exists()


def test_right_click_deletes_a_gallery_tile(page, live_server, logged_in, desktop, character):
    page.goto(f"{list_url(character)}?v=galeria")
    delete_by_menu(page, page.locator(".tile", has_text="Kael"))
    expect(page.locator(".tile")).to_have_count(0)
    assert not Record.objects.filter(pk=character.pk).exists()


def test_deleting_the_open_filter_goes_back_to_all(page, live_server, logged_in, desktop, character):
    group = ListGroup.objects.create(record_type=character.record_type, name="Taverna")
    character.group = group
    character.save()
    page.goto(f"{list_url(character)}?g={group.id}")
    delete_by_menu(page, page.get_by_role("link", name="Taverna"))
    expect(page).to_have_url(list_url(character) + "?")
    expect(page.get_by_role("link", name="Kael")).to_be_visible()
    expect(page.get_by_role("link", name="Taverna")).to_have_count(0)


def test_deleting_another_tab_keeps_the_open_one(page, live_server, logged_in, desktop, character):
    add_record_tab(character, "Notas")
    page.goto(f"/r/{character.id}/")
    page.evaluate("window.sameDocument = true")
    delete_by_menu(page, page.get_by_role("link", name="Notas", exact=True))
    expect(page.get_by_role("link", name="Notas", exact=True)).to_have_count(0)
    assert page.evaluate("window.sameDocument") is True


def test_deleting_the_open_tab_returns_to_the_record(page, live_server, logged_in, desktop, character):
    tab = add_record_tab(character, "Notas")
    Block.objects.create(tab=tab, kind="text", content=doc("nota"))
    page.goto(f"/r/{character.id}/?aba={tab.id}")
    delete_by_menu(page, page.get_by_role("link", name="Notas", exact=True))
    expect(page).to_have_url(f"/r/{character.id}/")
    expect(page.get_by_role("link", name="Notas", exact=True)).to_have_count(0)
    assert not Tab.objects.filter(pk=tab.pk).exists()


def test_deleting_a_file_from_the_gallery(page, live_server, logged_in, desktop, character):
    store_upload(character, None, small_png())
    page.goto(f"/r/{character.id}/?aba=galeria")
    delete_by_menu(page, page.locator(".gal-img"))
    expect(page.locator(".gal-item")).to_have_count(0)
    assert not character.asset_set.exists()


def test_escape_outside_click_and_scroll_close_the_menu(page, live_server, logged_in, desktop, campaign, character):
    for n in range(40):
        make_record(campaign, "Personagens", f"Extra {n}")
    page.goto(list_url(character))
    row = page.get_by_role("link", name="Kael")
    row.click(button="right")
    expect(menu(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu(page)).to_be_hidden()
    row.click(button="right")
    page.mouse.click(5, 400)
    expect(menu(page)).to_be_hidden()
    row.click(button="right")
    page.mouse.wheel(0, -300)
    expect(menu(page)).to_be_hidden()
    assert Record.objects.filter(pk=character.pk).exists()


def test_escape_on_the_menu_does_not_close_the_panel(page, live_server, logged_in, desktop, campaign, character):
    make_record(campaign, "Personagens", "Mira")
    page.goto(list_url(character))
    page.get_by_role("link", name="Kael").click()
    expect(page.locator("[data-sheet]")).to_be_visible()
    page.get_by_role("link", name="Mira").click(button="right")
    expect(menu(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu(page)).to_be_hidden()
    expect(page.locator("[data-sheet]")).to_be_visible()


def test_deleting_the_record_of_the_open_panel_closes_it(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character))
    page.get_by_role("link", name="Kael").click()
    expect(page.get_by_role("link", name="Expandir")).to_be_visible()
    delete_by_menu(page, page.get_by_role("link", name="Kael"))
    expect(page.locator("[data-sheet]")).to_be_hidden()
    expect(page).to_have_url(list_url(character))


def test_keyboard_opens_and_runs_the_menu_and_focus_stays_in_the_list(page, live_server, logged_in, desktop, campaign, character):
    make_record(campaign, "Personagens", "Mira")
    page.goto(list_url(character))
    page.get_by_role("link", name="Kael").focus()
    page.get_by_role("link", name="Kael").dispatch_event("contextmenu", {"clientX": 100, "clientY": 100})
    expect(menu(page)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("link", name="Mira")).to_be_focused()


# Celular


def test_long_press_opens_the_menu_and_stays_on_the_page(page, live_server, logged_in, character):
    page.goto(list_url(character))
    row = page.get_by_role("link", name="Kael")
    long_press(page, row)
    expect(menu(page)).to_be_visible()
    expect(page).to_have_url(list_url(character))
    box = menu(page).bounding_box()
    assert box["height"] >= 44 and box["x"] + box["width"] <= 390
    menu(page).click()
    expect(page.get_by_role("link", name="Kael")).to_have_count(0)
    assert not Record.objects.filter(pk=character.pk).exists()
    expect(page.locator("[data-sheet]")).to_be_hidden()


def test_short_tap_still_opens_the_panel(page, live_server, logged_in, character):
    page.goto(list_url(character))
    long_press(page, page.get_by_role("link", name="Kael"), hold_ms=60)
    expect(menu(page)).to_be_hidden()
    expect(page.locator("[data-sheet]")).to_be_visible()


def test_moving_the_finger_cancels_the_long_press(page, live_server, logged_in, character):
    page.goto(list_url(character))
    long_press(page, page.get_by_role("link", name="Kael"), move=40)
    expect(menu(page)).to_be_hidden()


# Menu nativo


def test_native_menu_stays_in_editor_and_inputs(page, live_server, logged_in, desktop, character):
    tab = character.tab_set.first()
    page.goto(f"/r/{character.id}/?aba={tab.id}")
    page.evaluate("""() => {
        window.prevented = [];
        document.addEventListener("contextmenu", (e) => { window.prevented.push(e.defaultPrevented); });
    }""")
    page.locator("[data-editor=text] [contenteditable]").click(button="right")
    expect(menu(page)).to_be_hidden()
    page.locator(".fields input").first.click(button="right")
    expect(menu(page)).to_be_hidden()
    assert page.evaluate("window.prevented") == [False, False]


def test_native_menu_stays_with_selected_text(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character))
    page.evaluate("""() => {
        const range = document.createRange();
        range.selectNodeContents(document.querySelector("h1"));
        getSelection().addRange(range);
    }""")
    page.get_by_role("link", name="Kael").click(button="right")
    expect(menu(page)).to_be_hidden()


def test_item_without_delete_url_keeps_native_menu(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character))
    page.locator("h1").click(button="right")
    expect(menu(page)).to_be_hidden()


def test_block_is_not_in_the_menu(page, live_server, logged_in, desktop, character):
    page.goto(f"/r/{character.id}/")
    page.locator(".block").first.click(button="right", position={"x": 2, "y": 2})
    expect(menu(page)).to_be_hidden()


# Falha


@pytest.mark.parametrize("answer", [
    {"status": 500, "body": "erro"},
    {"status": 404, "body": "nada"},
    {"status": 200, "body": "<html>aguarde</html>", "content_type": "text/html"},
])
def test_server_failure_keeps_the_item_and_warns(page, live_server, logged_in, desktop, character, answer):
    page.goto(list_url(character))
    page.route("**/apagar/", lambda route: route.fulfill(**answer))
    delete_by_menu(page, page.get_by_role("link", name="Kael"))
    expect(page.get_by_role("alert")).to_contain_text("Não foi possível deletar")
    expect(page.get_by_role("link", name="Kael")).to_be_visible()


def test_network_failure_keeps_the_item_and_warns(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character))
    page.route("**/apagar/", lambda route: route.abort())
    delete_by_menu(page, page.get_by_role("link", name="Kael"))
    expect(page.get_by_role("alert")).to_contain_text("Não foi possível deletar")
    expect(page.get_by_role("link", name="Kael")).to_be_visible()


def test_expired_session_keeps_the_item_and_says_so(page, live_server, logged_in, desktop, character):
    page.goto(list_url(character))
    csrf = [c for c in page.context.cookies() if c["name"] == "csrftoken"]
    page.context.clear_cookies()
    page.context.add_cookies(csrf)
    delete_by_menu(page, page.get_by_role("link", name="Kael"))
    expect(page.get_by_role("alert")).to_contain_text("Sessão expirada")
    expect(page.get_by_role("link", name="Kael")).to_be_visible()
    assert Record.objects.filter(pk=character.pk).exists()


# Personalizar


@pytest.fixture
def long_template(character):
    for n in range(12):
        FieldDef.objects.create(record_type=character.record_type, label=f"Campo {n}", kind="short", position=20 + n)
    return character


def test_personalizar_moves_without_jumping_or_reloading(page, live_server, logged_in, long_template):
    url = template_url(long_template)
    page.goto(url)
    page.evaluate("window.sameDocument = true")
    button = page.get_by_role("button", name="Subir Campo 9", exact=True)
    button.scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, 200)")
    before = page.evaluate("window.scrollY")
    assert before > 300
    with page.expect_response(lambda r: "/mover/" in r.url) as answer:
        button.click()
    assert answer.value.status == 200
    expect(page.get_by_role("button", name="Subir Campo 9", exact=True)).to_be_focused()
    assert page.evaluate("window.scrollY") == before
    assert page.evaluate("window.sameDocument") is True
    expect(page).to_have_url(url)


def test_personalizar_add_rename_remove_keep_the_scroll(page, live_server, logged_in, long_template):
    url = template_url(long_template)
    page.goto(url)
    page.evaluate("window.sameDocument = true")
    add = page.get_by_placeholder("Nova sub-aba da lista")
    add.scroll_into_view_if_needed()
    before = page.evaluate("window.scrollY")
    add.fill("Taverna")
    add.press("Enter")
    row = page.locator("li", has=page.get_by_role("button", name="Remover Taverna"))
    expect(row).to_be_visible()
    assert page.evaluate("window.scrollY") == before
    expect(add).to_be_focused()
    expect(add).to_have_value("")
    row.get_by_role("textbox").fill("Forja")
    row.get_by_role("button", name="Salvar").click()
    expect(page.get_by_role("button", name="Remover Forja")).to_be_visible()
    page.get_by_role("button", name="Remover Forja").click()
    expect(page.get_by_role("button", name="Remover Forja")).to_have_count(0)
    assert page.evaluate("window.sameDocument") is True
    assert ListGroup.objects.count() == 0
    expect(page).to_have_url(url)


def test_personalizar_works_without_js(browser, live_server, user, client, long_template):
    client.force_login(user)
    context = browser.new_context(java_script_enabled=False, base_url=live_server.url)
    context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                          "url": live_server.url}])
    page = context.new_page()
    page.goto(template_url(long_template))
    page.get_by_role("button", name="Remover Campo 3", exact=True).click()
    expect(page.get_by_role("button", name="Remover Campo 3", exact=True)).to_have_count(0)
    expect(page).to_have_url(template_url(long_template))
    context.close()


def test_personalizar_failure_warns_and_keeps_the_form(page, live_server, logged_in, long_template):
    page.goto(template_url(long_template))
    page.route("**/remover/", lambda route: route.fulfill(status=500, body="erro"))
    page.get_by_role("button", name="Remover Campo 3", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("Não foi possível concluir")
    expect(page.get_by_role("button", name="Remover Campo 3", exact=True)).to_be_visible()


def test_personalizar_expired_session_goes_to_login(page, live_server, logged_in, long_template):
    page.goto(template_url(long_template))
    csrf = [c for c in page.context.cookies() if c["name"] == "csrftoken"]
    page.context.clear_cookies()
    page.context.add_cookies(csrf)
    page.get_by_role("button", name="Remover Campo 3", exact=True).click()
    expect(page.locator("input[type=password]")).to_be_visible()


def test_back_button_after_personalizar_leaves_the_screen(page, live_server, logged_in, long_template):
    page.goto(list_url(long_template))
    page.goto(template_url(long_template))
    page.get_by_role("button", name="Remover Campo 3", exact=True).click()
    expect(page.get_by_role("button", name="Remover Campo 3", exact=True)).to_have_count(0)
    page.go_back()
    expect(page).to_have_url(list_url(long_template))
    expect(page.get_by_role("link", name="Kael")).to_be_visible()


# Registro e lista


def create_in_strip(page, nav, name):
    strip = page.get_by_role("navigation", name=nav, exact=True)
    strip.locator("summary").click()
    strip.get_by_role("textbox").fill(name)
    strip.get_by_role("button", name="Criar").click()


def test_new_filter_appears_without_reloading(page, live_server, logged_in, character):
    page.goto(list_url(character))
    page.evaluate("window.sameDocument = true")
    create_in_strip(page, "Sub-abas da lista", "Taverna")
    expect(page.get_by_role("link", name="Taverna")).to_be_focused()
    assert page.evaluate("window.sameDocument") is True
    expect(page).to_have_url(list_url(character))


def test_new_tab_keeps_unsaved_text_of_the_open_tab(page, live_server, logged_in, character):
    page.goto(f"/r/{character.id}/")
    page.evaluate("window.sameDocument = true")
    box = page.locator("[data-editor=text] [contenteditable]").first
    box.click()
    page.keyboard.type(" novo")
    create_in_strip(page, "Abas", "Notas")
    expect(page.get_by_role("link", name="Notas", exact=True)).to_be_focused()
    expect(box).to_contain_text("texto novo")
    assert page.evaluate("window.sameDocument") is True
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert Block.objects.get(tab__record=character).content == doc("texto novo")


def test_new_subtab_and_block_appear_without_reloading(page, live_server, logged_in, character):
    page.goto(f"/r/{character.id}/")
    page.evaluate("window.sameDocument = true")
    create_in_strip(page, "Sub-abas", "Filha")
    expect(page.get_by_role("link", name="Filha")).to_be_visible()
    page.get_by_role("button", name="+ Texto").click()
    new = page.locator("[data-editor=text] [contenteditable]").nth(1)
    new.click()
    page.keyboard.type("bloco novo")
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert page.evaluate("window.sameDocument") is True
    assert character.tab_set.get(title=character.tab_set.first().title).block_set.count() == 2
    assert Block.objects.filter(content=doc("bloco novo")).exists()


def test_embed_appears_without_reloading(page, live_server, logged_in, character, elf):
    page.goto(f"/r/{character.id}/")
    page.evaluate("window.sameDocument = true")
    page.locator(".picker summary").click()
    page.get_by_role("combobox").fill("elf")
    page.get_by_role("option", name="Elfos").first.click()
    expect(page.locator(".embed-block")).to_contain_text("base")
    expect(page.locator(".picker")).not_to_have_attribute("open", "")
    assert page.evaluate("window.sameDocument") is True


def test_remove_block_and_file_buttons_do_not_reload(page, live_server, logged_in, character):
    tab = character.tab_set.first()
    Block.objects.create(tab=tab, kind="text", content=doc("outro"), position=2)
    store_upload(character, tab, small_png())
    store_upload(character, tab, small_png("b.png"))  # a primeira imagem já nasce principal
    page.goto(f"/r/{character.id}/")
    page.evaluate("window.sameDocument = true")
    page.get_by_role("button", name="Tornar principal").click()
    expect(page.locator(".gal-item").first.locator(".gal-actions")).to_contain_text("Principal")
    for remaining in (1, 0):
        page.locator(".gal-actions summary").first.click()
        page.get_by_role("button", name="Confirmar exclusão").first.click()
        expect(page.locator(".gal-item")).to_have_count(remaining)
    expect(page.get_by_text("Sem arquivos.")).to_be_visible()
    page.locator(".text-block summary").first.click()
    page.get_by_role("button", name="Confirmar remoção").first.click()
    expect(page.locator(".text-block")).to_have_count(1)
    assert page.evaluate("window.sameDocument") is True
