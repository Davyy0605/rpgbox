import os

from playwright.sync_api import expect

from campaigns.models import ListGroup

from ..test_indexing import make_record
from .test_deleting import delete_by_menu, desktop, list_url  # noqa: F401


def shot(page, name):
    # Fotos para conferir o visual: RPGBOX_SHOTS=<pasta> pytest tests/e2e/test_welcome.py
    folder = os.environ.get("RPGBOX_SHOTS")
    if folder:
        page.wait_for_timeout(200)
        page.screenshot(path=f"{folder}/{name}.png", full_page=True)


def test_first_visit_explains_the_steps(page, live_server, logged_in):
    page.goto("/")
    expect(page.get_by_role("heading", name="Boas-vindas ao RPGBox")).to_be_visible()
    expect(page.locator(".steps li")).to_have_count(3)
    expect(page.get_by_role("heading", name="Comece pela sua campanha")).to_be_visible()
    shot(page, "1-primeira-entrada")


def test_steps_leave_once_there_is_a_campaign(page, live_server, logged_in, campaign):
    page.goto("/")
    expect(page.get_by_role("heading", name="Campanhas")).to_be_visible()
    expect(page.locator(".steps")).to_have_count(0)
    expect(page.get_by_role("heading", name="Nova campanha")).to_be_visible()
    expect(page.locator(".empty")).to_be_hidden()
    shot(page, "2-campanhas")


def test_empty_list_explains_itself(page, live_server, logged_in, campaign):
    rtype = campaign.recordtype_set.first()
    page.goto(f"/c/{campaign.id}/t/{rtype.id}/")
    expect(page.get_by_text("0 registros")).to_be_visible()
    expect(page.get_by_role("heading", name="Nada por aqui ainda")).to_be_visible()
    expect(page.get_by_role("link", name=f"+ Novo em {rtype.name}")).to_be_visible()
    shot(page, "3-lista-vazia")


def test_list_count_follows_the_delete_menu_until_the_empty_message(page, live_server, logged_in, campaign, character):
    other = make_record(campaign, character.record_type.name, "Thorek")
    page.goto(list_url(character))
    expect(page.get_by_text("2 registros")).to_be_visible()
    expect(page.locator(".empty")).to_be_hidden()
    expect(page.locator(".row-img[data-i='T']")).to_be_visible()
    shot(page, "4-lista")
    delete_by_menu(page, page.get_by_role("link", name=other.name))
    expect(page.get_by_text("1 registro", exact=True)).to_be_visible()
    delete_by_menu(page, page.get_by_role("link", name=character.name))
    expect(page.get_by_text("0 registros")).to_be_visible()
    expect(page.locator(".empty")).to_be_visible()


def test_campaign_home_names_its_buttons(page, live_server, logged_in, campaign, character):
    page.goto(f"/c/{campaign.id}/")
    row = page.locator(".type-row", has_text=character.record_type.name)
    expect(row.get_by_text("1 registro", exact=True)).to_be_visible()
    expect(row.get_by_role("link", name=f"Novo em {character.record_type.name}")).to_have_text("+ Novo")
    expect(page.get_by_role("link", name="+ Criar tipo")).to_be_visible()
    expect(page.get_by_text("Ainda vazio").first).to_be_visible()
    shot(page, "5-campanha")


def test_record_tabs_have_named_buttons(page, live_server, logged_in, character):
    page.goto(f"/r/{character.id}/")
    expect(page.locator("#abas summary").first).to_have_text("+ Nova aba")
    shot(page, "6-ficha")


def test_group_keeps_count_and_explains_when_empty(page, live_server, logged_in, desktop, campaign, character):
    group = ListGroup.objects.create(record_type=character.record_type, name="Vilões")
    page.goto(f"{list_url(character)}?g={group.id}")
    expect(page.get_by_role("heading", name="Nada neste grupo ainda")).to_be_visible()
    page.goto(list_url(character))
    delete_by_menu(page, page.get_by_role("navigation", name="Grupos da lista").get_by_role("link", name="Vilões"))
    expect(page.get_by_role("navigation", name="Grupos da lista").get_by_role("link", name="Vilões")).to_have_count(0)
    expect(page.get_by_text("1 registro", exact=True)).to_be_visible()
