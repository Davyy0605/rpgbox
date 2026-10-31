import pytest

from campaigns.models import ListGroup

from ..test_indexing import make_record

LONG = "Arquimedes" * 12  # 120 letras sem espaço: o pior caso para quebrar a tela
SCREENS = [
    "home", "campaigns", "campaign", "type_new", "list", "list_empty", "record_new", "detail", "detail_panel",
    "gallery", "template", "search", "copy", "bulk", "delete",
]


@pytest.fixture
def paths(campaign, character, elf):
    kael = character
    make_record(campaign, "Personagens", LONG, body=LONG)
    ListGroup.objects.create(record_type=kael.record_type, name=LONG)
    base = f"/c/{campaign.id}"
    tid = kael.record_type_id
    return {
        "home": "/", "campaigns": "/c/", "campaign": f"{base}/", "type_new": f"{base}/tipos/novo/",
        "list": f"{base}/t/{tid}/", "list_empty": f"{base}/t/{campaign.recordtype_set.get(name='Regiões').id}/",
        "record_new": f"{base}/t/{tid}/novo/", "detail": f"/r/{kael.id}/",
        "detail_panel": f"/r/{kael.id}/?painel={elf.id}", "gallery": f"/r/{kael.id}/?aba=galeria",
        "template": f"{base}/t/{tid}/modelo/", "search": f"{base}/busca/?q=a", "copy": f"/r/{kael.id}/copiar/",
        "bulk": f"{base}/t/{campaign.recordtype_set.get(name='Trilhas').id}/trilhas/", "delete": f"/r/{kael.id}/apagar/",
    }


@pytest.mark.parametrize("screen", SCREENS)
def test_no_horizontal_scroll_at_390(page, logged_in, paths, screen):
    page.goto(paths[screen])
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("screen", SCREENS)
def test_touch_targets_are_44px(page, logged_in, paths, screen):
    page.goto(paths[screen])
    # Só links de menção dentro de texto corrido ficam fora (a.mention e links dentro de parágrafos/listas
    # do texto): o alvo é a palavra. Botões, campos e abas continuam checados em toda a tela.
    small = page.evaluate("""[...document.querySelectorAll('a,button,summary,select,input:not([type=hidden])')]
        .filter(e => !(e.tagName === 'A' && e.closest('.ProseMirror p, .ProseMirror li, .embed-body p, .embed-body li, .sheet-section p, .sheet-section li, .field-body p')) && e.getClientRects().length)
        .filter(e => e.getBoundingClientRect().height < 43.5)
        .map(e => e.outerHTML.slice(0, 80))""")
    assert small == []


def test_add_popover_fits_at_390(page, logged_in, paths):
    page.goto(paths["list"])
    page.locator(".add summary").first.click()
    box = page.locator(".add[open] form").first.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
