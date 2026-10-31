import pytest
from django.core.exceptions import ValidationError

from campaigns.models import ListGroup, TabDef
from records.models import Block, Record, Tab
from records.services import add_record_tab, add_subtab, create_record, visible_fields, visible_tabs

from .helpers import doc


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def character(campaign):
    return create_record(campaign.recordtype_set.get(name="Personagens"), "Kael")


@pytest.fixture
def tracks(campaign):
    t = campaign.recordtype_set.get(name="Trilhas")
    g = ListGroup.objects.create(record_type=t, name="Taverna")
    create_record(t, "Taberna", group=g)
    create_record(t, "Duelo")
    return t


def test_new_record_has_template_tabs(character):
    assert [t.title for t in visible_tabs(character)] == ["Ficha", "Habilidades", "Magias", "História"]


def test_new_template_tab_appears_empty_on_existing_record(character):
    TabDef.objects.create(record_type=character.record_type, title="Raça", position=9)
    assert "Raça" in [t.title for t in visible_tabs(character)]


def test_removed_tab_stays_while_it_has_content(character):
    tab = visible_tabs(character)[0]
    Block.objects.create(tab=tab, kind="text", content=doc("oi"), position=0)
    tab.tab_def.removed = True; tab.tab_def.save()
    assert tab.title in [t.title for t in visible_tabs(character)]
    assert tab.title not in [t.title for t in visible_tabs(create_record(character.record_type, "Novo"))]


def test_removed_empty_tab_hidden_on_existing_record(character):
    d = character.record_type.tabdef_set.get(title="Magias"); d.removed = True; d.save()
    assert "Magias" not in [t.title for t in visible_tabs(character)]


def test_removed_empty_field_hidden_filled_field_kept(character):
    f = character.record_type.fielddef_set.get(label="Idade")
    f.removed = True; f.save()
    assert f not in [x for x, _ in visible_fields(character)]
    character.fields[f.key] = 34; character.save()
    assert f in [x for x, _ in visible_fields(character)]


def test_renaming_tabdef_renames_tab(character):
    d = character.record_type.tabdef_set.get(title="Ficha"); d.title = "Atributos"; d.save()
    assert "Atributos" in [t.title for t in visible_tabs(character)]


def test_subtab_only_one_level(character):
    sub = add_subtab(visible_tabs(character)[0], "Fogo")
    with pytest.raises(ValidationError):
        add_subtab(sub, "Chama")


def test_subtab_appears_as_child_and_record_tab_at_end(character):
    top = visible_tabs(character)[0]
    add_subtab(top, "Fogo"); add_record_tab(character, "Segredos")
    tabs = visible_tabs(character)
    assert [c.title for c in tabs[0].children] == ["Fogo"]
    assert tabs[-1].title == "Segredos"
    assert "Fogo" not in [t.title for t in tabs]


def test_list_group_filter(client, user, tracks):
    client.force_login(user)
    r = client.get(f"/c/{tracks.campaign_id}/t/{tracks.id}/?g={tracks.listgroup_set.first().id}")
    assert b"Taberna" in r.content and b"Duelo" not in r.content


def test_list_all_and_gallery_view(client, user, tracks):
    client.force_login(user)
    r = client.get(f"/c/{tracks.campaign_id}/t/{tracks.id}/")
    assert b"Taberna" in r.content and b"Duelo" in r.content
    r = client.get(f"/c/{tracks.campaign_id}/t/{tracks.id}/?v=galeria")
    assert r.status_code == 200 and b"Duelo" in r.content


def test_list_foreign_group_shows_all_without_leaking(client, user, other_user, make_campaign, tracks, campaign):
    other_type = ListGroup.objects.create(record_type=campaign.recordtype_set.get(name="Itens"), name="Alheia")
    theirs = make_campaign(other_user, "Outra").recordtype_set.get(name="Trilhas")
    other_master = ListGroup.objects.create(record_type=theirs, name="Secreta")
    client.force_login(user)
    for g in (other_type, other_master):
        r = client.get(f"/c/{tracks.campaign_id}/t/{tracks.id}/?g={g.id}")
        assert r.status_code == 200 and r.context["current_group"] is None
        assert b"Taberna" in r.content and b"Duelo" in r.content and g.name.encode() not in r.content


def test_list_of_another_master_is_still_404(client, other_user, tracks):
    client.force_login(other_user)
    g = tracks.listgroup_set.first()
    assert client.get(f"/c/{tracks.campaign_id}/t/{tracks.id}/?g={g.id}").status_code == 404


def test_group_add_and_new_record_in_group(client, user, tracks):
    client.force_login(user)
    r = client.post(f"/c/{tracks.campaign_id}/t/{tracks.id}/grupos/novo/", {"name": "Combate"})
    g = tracks.listgroup_set.get(name="Combate")
    assert r.url == f"/c/{tracks.campaign_id}/t/{tracks.id}/?g={g.id}"
    r = client.post(f"/c/{tracks.campaign_id}/t/{tracks.id}/novo/", {"name": "Batalha", "group": g.id})
    rec = Record.objects.get(name="Batalha")
    assert r.url == f"/r/{rec.id}/" and rec.group == g


def test_new_record_rejects_group_of_other_type(client, user, tracks, campaign):
    g = ListGroup.objects.create(record_type=campaign.recordtype_set.get(name="Itens"), name="X")
    client.force_login(user)
    client.post(f"/c/{tracks.campaign_id}/t/{tracks.id}/novo/", {"name": "Batalha", "group": g.id})
    assert not Record.objects.filter(name="Batalha").exists()


def test_detail_shows_tabs_gallery_last_and_selected(client, user, character):
    client.force_login(user)
    r = client.get(f"/r/{character.id}/")
    html = r.content.decode()
    assert r.status_code == 200 and "Ficha" in html and html.rindex("Galeria") > html.rindex("História")
    tab = character.tab_set.get(title="Magias")
    assert client.get(f"/r/{character.id}/?aba={tab.id}").status_code == 200


def test_tab_and_subtab_add_views(client, user, character):
    client.force_login(user)
    r = client.post(f"/r/{character.id}/abas/nova/", {"title": "Segredos"})
    assert Tab.objects.filter(record=character, title="Segredos", parent=None).exists() and r.status_code == 302
    top = character.tab_set.get(title="Ficha")
    client.post(f"/r/{character.id}/abas/{top.id}/sub/", {"title": "Fogo"})
    sub = Tab.objects.get(title="Fogo")
    assert sub.parent == top
    client.post(f"/r/{character.id}/abas/{sub.id}/sub/", {"title": "Chama"})
    assert not Tab.objects.filter(title="Chama").exists()


def test_record_group_choice(client, user, tracks):
    rec = tracks.record_set.get(name="Duelo"); g = tracks.listgroup_set.first()
    client.force_login(user)
    client.post(f"/r/{rec.id}/grupo/", {"group": g.id})
    rec.refresh_from_db()
    assert rec.group == g


def test_panel_shows_basic_fields(client, user, character):
    f = character.record_type.fielddef_set.get(label="Ocupação")
    character.fields[f.key] = "Ladino"; character.save()
    client.force_login(user)
    r = client.get(f"/r/{character.id}/painel/")
    assert b"Kael" in r.content and b"Ladino" in r.content


def test_other_user_gets_404_on_record_views(client, other_user, character):
    client.force_login(other_user)
    for url in (f"/r/{character.id}/", f"/r/{character.id}/painel/",
                f"/c/{character.campaign_id}/t/{character.record_type_id}/"):
        assert client.get(url).status_code == 404
    assert client.post(f"/r/{character.id}/abas/nova/", {"title": "X"}).status_code == 404


def test_home_counts_records(client, user, character):
    client.force_login(user)
    r = client.get(f"/c/{character.campaign_id}/")
    assert r.status_code == 200
    assert [t.total for t in r.context["types"]][:1] == [1]


def test_create_type_from_home(client, user, campaign):
    client.force_login(user)
    r = client.post(f"/c/{campaign.id}/tipos/novo/", {"name": "Raças"})
    t = campaign.recordtype_set.get(name="Raças")
    assert r.url == f"/c/{campaign.id}/t/{t.id}/"
    assert client.post(f"/c/{campaign.id}/tipos/novo/", {"name": "Raças"}).status_code == 200


def test_field_key_with_nul_or_lone_surrogate_is_400_not_500(client, user, make_campaign):
    from tests.test_indexing import make_record
    record = make_record(make_campaign(user), "Personagens", "Kael")
    client.force_login(user)
    for key in ("\x00", "\ud800"):
        r = client.post(f"/r/{record.id}/campos/", {"key": key, "version": 1, "value": "x"}, content_type="application/json")
        assert r.status_code == 400
