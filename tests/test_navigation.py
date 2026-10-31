import pytest

from campaigns.models import ListGroup
from content.render import render_doc
from indexing.services import reindex_record, resolver_for
from records.models import Block
from records.services import add_record_tab, add_subtab, create_record

from .helpers import doc_headings, doc_mention
from .test_indexing import make_record

HEADINGS = doc_headings([(2, "visao", "Visão no Escuro"), "enxerga longe", (2, "fala", "Idioma"), "fala élfico"])


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def signed_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def character(campaign):
    return make_record(campaign, "Personagens", "Kael", body="texto")


@pytest.fixture
def elf(campaign):
    return make_record(campaign, "Raças", "Elfos", body="base")


def list_url(record):
    return f"/c/{record.campaign_id}/t/{record.record_type_id}/"


def in_second_tab(record, content, title="Segunda"):
    tab = add_record_tab(record, title)
    Block.objects.create(tab=tab, kind="text", content=content)
    return tab


# Painel


def test_panel_with_anchor_shows_only_that_section(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    html = signed_in.get(f"/r/{elf.id}/painel/?ancora=visao").content.decode()
    assert "enxerga longe" in html
    assert "fala élfico" not in html


def test_panel_with_anchor_expands_to_the_passage(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    html = signed_in.get(f"/r/{elf.id}/painel/?ancora=visao").content.decode()
    assert f'href="/r/{elf.id}/?trecho=visao#visao"' in html


def test_panel_finds_anchor_in_long_field(signed_in, character):
    key = character.record_type.fielddef_set.get(kind="long").key
    character.fields[key] = HEADINGS
    character.save()
    html = signed_in.get(f"/r/{character.id}/painel/?ancora=fala").content.decode()
    assert "fala élfico" in html and "enxerga longe" not in html


def test_panel_with_unknown_anchor_shows_the_whole_panel(signed_in, character):
    f = character.record_type.fielddef_set.get(label="Ocupação")
    character.fields[f.key] = "Ladino"
    character.save()
    html = signed_in.get(f"/r/{character.id}/painel/?ancora=nada").content.decode()
    assert "Ladino" in html


def test_panel_close_is_a_real_control_not_a_link_to_the_list(signed_in, character):
    html = signed_in.get(f"/r/{character.id}/painel/").content.decode()
    assert "data-sheet-close" in html
    assert f'href="{list_url(character)}"' not in html


def test_list_with_painel_opens_the_panel(signed_in, character):
    html = signed_in.get(f"{list_url(character)}?painel={character.id}").content.decode()
    assert "data-sheet" in html and "Expandir" in html


def test_list_keeps_group_with_panel_open(signed_in, campaign):
    rtype = campaign.recordtype_set.get(name="Personagens")
    group = ListGroup.objects.create(record_type=rtype, name="Grupo")
    inside = create_record(rtype, "Dentro", group=group)
    create_record(rtype, "Fora")
    html = signed_in.get(f"/c/{campaign.id}/t/{rtype.id}/?g={group.id}&painel={inside.id}").content.decode()
    assert "data-sheet" in html and "Fora" not in html


def test_list_with_painel_accepts_target_of_another_type(signed_in, character, elf):
    html = signed_in.get(f"{list_url(character)}?painel={elf.id}").content.decode()
    assert "data-sheet" in html and "Elfos" in html


def test_list_with_painel_and_anchor_shows_the_section(signed_in, character, elf):
    in_second_tab(elf, HEADINGS)
    html = signed_in.get(f"{list_url(character)}?painel={elf.id}&ancora=visao").content.decode()
    assert "enxerga longe" in html and "fala élfico" not in html


def test_detail_with_painel_opens_the_panel(signed_in, character, elf):
    html = signed_in.get(f"/r/{character.id}/?painel={elf.id}").content.decode()
    assert "data-sheet" in html and 'aria-label="Elfos"' in html


@pytest.mark.parametrize("value", ["", "abc", "-1", "9" * 40, "٣"])
def test_invalid_painel_is_ignored(signed_in, character, value):
    r = signed_in.get(list_url(character), {"painel": value})
    assert r.status_code == 200 and b"data-sheet" not in r.content


def test_panel_of_another_user_stays_closed_and_reveals_nothing(signed_in, character, other_user, make_campaign):
    foreign = make_record(make_campaign(other_user, "Dela"), "Personagens", "Segredo")
    r = signed_in.get(f"{list_url(character)}?painel={foreign.id}")
    assert r.status_code == 200 and b"data-sheet" not in r.content and b"Segredo" not in r.content


def test_panel_of_another_campaign_stays_closed(signed_in, character, user, make_campaign):
    other = make_record(make_campaign(user, "Outra"), "Personagens", "Distante")
    r = signed_in.get(f"{list_url(character)}?painel={other.id}")
    assert b"data-sheet" not in r.content and b"Distante" not in r.content


def test_list_rows_open_the_panel_and_keep_the_full_screen_link(signed_in, character):
    html = signed_in.get(list_url(character)).content.decode()
    assert f'data-panel-url="/r/{character.id}/painel/"' in html
    assert f'href="/r/{character.id}/"' in html
    assert "hx-get" not in html.split('<ul class="list"')[1].split("</ul>")[0]


# Âncora na tela completa


def test_mention_to_heading_goes_to_the_passage_and_opens_quick_view(elf):
    html = render_doc(doc_mention(elf.id, "Elfos", "visao"), resolver_for(elf.campaign))
    assert f'href="/r/{elf.id}/?trecho=visao#visao"' in html
    assert f'data-panel-url="/r/{elf.id}/painel/?ancora=visao"' in html


def test_mention_without_anchor_opens_quick_view(elf):
    html = render_doc(doc_mention(elf.id, "Elfos"), resolver_for(elf.campaign))
    assert f'href="/r/{elf.id}/"' in html and f'data-panel-url="/r/{elf.id}/painel/"' in html


def test_deleted_mention_has_no_panel(elf):
    html = render_doc(doc_mention(elf.id + 99, "Antigo"), resolver_for(elf.campaign))
    assert "data-panel-url" not in html


def test_detail_opens_tab_of_the_heading(signed_in, elf):
    tab = in_second_tab(elf, HEADINGS)
    r = signed_in.get(f"/r/{elf.id}/?trecho=visao")
    assert r.context["selected"] == tab
    assert b"Vis\\u00e3o no Escuro" in r.content or "Visão no Escuro".encode() in r.content


def test_detail_opens_subtab_of_the_heading(signed_in, elf):
    tab = add_record_tab(elf, "Segunda")
    sub = add_subtab(tab, "Dentro")
    Block.objects.create(tab=sub, kind="text", content=HEADINGS)
    r = signed_in.get(f"/r/{elf.id}/?trecho=fala")
    assert r.context["selected"] == sub and r.context["parent"].id == tab.id


def test_detail_explicit_tab_wins_over_anchor(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    first = elf.tab_set.order_by("position", "id").first()
    r = signed_in.get(f"/r/{elf.id}/?aba={first.id}&trecho=visao")
    assert r.context["selected"].id == first.id


def test_detail_with_unknown_anchor_opens_first_tab(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    r = signed_in.get(f"/r/{elf.id}/?trecho=nada")
    assert r.context["selected"].id == elf.tab_set.order_by("position", "id").first().id


def test_search_result_links_to_the_passage(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    reindex_record(elf)
    html = signed_in.get(f"/c/{elf.campaign_id}/busca/?q=escuro", headers={"HX-Request": "true"}).content.decode()
    assert f'href="/r/{elf.id}/?trecho=visao#visao"' in html


def test_embed_origin_links_to_the_passage(signed_in, character, elf):
    in_second_tab(elf, HEADINGS)
    tab = character.tab_set.order_by("position", "id").first()
    Block.objects.create(tab=tab, kind="embed", embed_record=elf, embed_anchor="visao", embed_label="Elfos")
    html = signed_in.get(f"/r/{character.id}/").content.decode()
    assert f'href="/r/{elf.id}/?trecho=visao#visao"' in html


# Caminho


def test_pages_report_their_crumb(signed_in, character):
    home = signed_in.get(f"/c/{character.campaign_id}/").content.decode()
    assert 'data-crumb="Vael"' in home and f'data-crumb-url="/c/{character.campaign_id}/"' in home
    listing = signed_in.get(list_url(character)).content.decode()
    assert 'data-crumb="Personagens"' in listing and f'data-crumb-url="{list_url(character)}"' in listing
    detail = signed_in.get(f"/r/{character.id}/").content.decode()
    assert 'data-crumb="Kael"' in detail and f'data-crumb-url="/r/{character.id}/"' in detail


def test_panel_reports_its_crumb(signed_in, character):
    html = signed_in.get(f"/r/{character.id}/painel/").content.decode()
    assert 'data-crumb="Kael"' in html and f'data-crumb-url="/r/{character.id}/"' in html


def test_section_crumb_names_the_heading(signed_in, elf):
    in_second_tab(elf, HEADINGS)
    for url in (f"/r/{elf.id}/painel/?ancora=visao", f"/r/{elf.id}/?trecho=visao"):
        html = signed_in.get(url).content.decode()
        assert 'data-crumb="Elfos › Visão no Escuro"' in html
        assert f'data-crumb-url="/r/{elf.id}/?trecho=visao#visao"' in html


def test_every_page_has_the_trail_slot(signed_in, character):
    assert b"data-trail" in signed_in.get(f"/r/{character.id}/").content


# Busca em toda a campanha


def test_search_is_on_every_campaign_screen(signed_in, character):
    c, t = character.campaign_id, character.record_type_id
    for url in (f"/c/{c}/t/{t}/", f"/c/{c}/t/{t}/novo/", f"/c/{c}/tipos/novo/", f"/r/{character.id}/",
                f"/r/{character.id}/apagar/", f"/r/{character.id}/copiar/"):
        r = signed_in.get(url)
        assert r.status_code == 200, url
        assert f'hx-get="/c/{c}/busca/"'.encode() in r.content, url


def test_home_and_results_keep_a_single_search(signed_in, character):
    c = character.campaign_id
    for url in (f"/c/{c}/", f"/c/{c}/busca/?q=k"):
        assert signed_in.get(url).content.count(b"data-search-input") == 1, url


def test_search_is_not_shown_outside_a_campaign(signed_in, character):
    assert b"data-search-input" not in signed_in.get("/campanhas/").content


# Lista


def test_list_filter_is_wired(signed_in, character):
    assert b"data-list-filter" in signed_in.get(list_url(character)).content


def test_list_of_tracks_has_copy_button_with_the_link(signed_in, campaign):
    track = make_record(campaign, "Trilhas", "Tema")
    key = track.record_type.fielddef_set.get(kind="link").key
    track.fields[key] = "https://exemplo.com/tema"
    track.save()
    html = signed_in.get(list_url(track)).content.decode()
    assert 'data-copy="https://exemplo.com/tema"' in html


def test_list_row_without_link_has_no_copy_button(signed_in, campaign):
    track = make_record(campaign, "Trilhas", "Tema")
    assert b"data-copy" not in signed_in.get(list_url(track)).content


def test_list_does_not_copy_an_unsafe_link(signed_in, campaign):
    track = make_record(campaign, "Trilhas", "Tema")
    key = track.record_type.fielddef_set.get(kind="link").key
    track.fields[key] = "javascript:alert(1)"
    track.save()
    assert b"data-copy" not in signed_in.get(list_url(track)).content
