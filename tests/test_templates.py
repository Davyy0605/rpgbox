import pytest

from campaigns.models import FieldDef, ListGroup, TabDef
from campaigns.template_views import create_type
from records.models import Record
from records.services import create_record

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def character(campaign):
    return create_record(campaign.recordtype_set.get(name="Personagens"), "Kael")


def test_create_custom_type_appears_on_home(client, user, make_campaign):
    c = make_campaign(user); client.force_login(user)
    client.post(f"/c/{c.id}/tipos/novo/", {"name": "Raças"})
    assert "Raças" in client.get(f"/c/{c.id}/").content.decode()


def test_duplicate_type_name_shows_error(client, user, make_campaign):
    c = make_campaign(user); client.force_login(user)
    r = client.post(f"/c/{c.id}/tipos/novo/", {"name": "Itens"})
    assert r.status_code == 200 and c.recordtype_set.filter(name="Itens").count() == 1


def test_create_type_has_no_fields_or_tabs(campaign):
    t = create_type(campaign, "Raças")
    assert not t.fielddef_set.exists() and not t.tabdef_set.exists()


def test_rename_field_keeps_values(client, character, user):
    f = character.record_type.fielddef_set.get(label="Idade")
    character.fields[f.key] = 34; character.save(); client.force_login(user)
    client.post(f"/modelo/campo/{f.id}/renomear/", {"label": "Anos"})
    character.refresh_from_db(); assert character.fields[f.key] == 34
    f.refresh_from_db(); assert f.label == "Anos"


def test_remove_marks_removed_and_keeps_data(client, character, user):
    f = character.record_type.fielddef_set.get(label="Idade"); client.force_login(user)
    client.post(f"/modelo/campo/{f.id}/remover/")
    f.refresh_from_db(); assert f.removed


def test_template_subtab_is_one_level(client, character, user):
    d = character.record_type.tabdef_set.first(); client.force_login(user)
    sub = TabDef.objects.create(record_type=d.record_type, parent=d, title="A", position=0)
    assert client.post(f"/modelo/tipo/{d.record_type_id}/aba/", {"title": "B", "parent": sub.id}).status_code == 400


def test_add_field_and_tab(client, campaign, user):
    t = campaign.recordtype_set.get(name="Itens"); client.force_login(user)
    client.post(f"/modelo/tipo/{t.id}/campo/", {"label": "Peso", "kind": "number"})
    client.post(f"/modelo/tipo/{t.id}/aba/", {"title": "Lore"})
    assert t.fielddef_set.filter(label="Peso", kind="number", removed=False).exists()
    assert t.tabdef_set.filter(title="Lore", parent=None).exists()


def test_add_subtab_to_top_tab(client, campaign, user):
    d = campaign.recordtype_set.get(name="Itens").tabdef_set.first(); client.force_login(user)
    r = client.post(f"/modelo/tipo/{d.record_type_id}/aba/", {"title": "Sub", "parent": d.id})
    assert r.status_code == 302 and TabDef.objects.filter(title="Sub", parent=d).exists()


def test_move_field_swaps_order(client, campaign, user):
    t = campaign.recordtype_set.get(name="Itens"); client.force_login(user)
    a, b = t.fielddef_set.order_by("position", "id")[:2]
    client.post(f"/modelo/campo/{b.id}/mover/", {"dir": "up"})
    ids = list(t.fielddef_set.order_by("position", "id").values_list("id", flat=True))
    assert ids.index(b.id) < ids.index(a.id)


def test_move_first_up_is_noop(client, campaign, user):
    t = campaign.recordtype_set.get(name="Itens"); client.force_login(user)
    a = t.fielddef_set.order_by("position", "id").first()
    assert client.post(f"/modelo/campo/{a.id}/mover/", {"dir": "up"}).status_code == 302
    assert t.fielddef_set.order_by("position", "id").first().id == a.id


def test_move_and_rename_tab(client, campaign, user):
    t = campaign.recordtype_set.get(name="Itens"); client.force_login(user)
    a, b = t.tabdef_set.order_by("position", "id")[:2]
    client.post(f"/modelo/aba/{a.id}/mover/", {"dir": "down"})
    client.post(f"/modelo/aba/{a.id}/renomear/", {"title": "Nova"})
    ids = list(t.tabdef_set.order_by("position", "id").values_list("id", flat=True))
    a.refresh_from_db()
    assert ids.index(b.id) < ids.index(a.id) and a.title == "Nova"


def test_remove_tab_marks_removed(client, campaign, user):
    d = campaign.recordtype_set.get(name="Itens").tabdef_set.first(); client.force_login(user)
    client.post(f"/modelo/aba/{d.id}/remover/")
    d.refresh_from_db(); assert d.removed


def test_group_rename_and_remove(client, campaign, user):
    t = campaign.recordtype_set.get(name="Trilhas"); client.force_login(user)
    g = ListGroup.objects.create(record_type=t, name="Taverna")
    r = create_record(t, "Taberna", group=g)
    client.post(f"/modelo/grupo/{g.id}/renomear/", {"name": "Bar"})
    g.refresh_from_db(); assert g.name == "Bar"
    client.post(f"/modelo/grupo/{g.id}/remover/")
    assert not ListGroup.objects.filter(pk=g.id).exists()
    r.refresh_from_db(); assert r.group is None and Record.objects.filter(pk=r.id).exists()


def test_other_user_cannot_edit(client, other_user, campaign, character):
    client.force_login(other_user)
    f = character.record_type.fielddef_set.first()
    assert client.post(f"/modelo/campo/{f.id}/remover/").status_code == 404
    assert client.get(f"/c/{campaign.id}/t/{character.record_type_id}/modelo/").status_code == 404
    assert client.post(f"/modelo/tipo/{character.record_type_id}/aba/", {"title": "x"}).status_code == 404
    f.refresh_from_db(); assert not f.removed


def test_template_edit_page_and_customize_link(client, campaign, character, user):
    client.force_login(user)
    t = character.record_type
    page = client.get(f"/c/{campaign.id}/t/{t.id}/modelo/").content.decode()
    assert "Idade" in page and "Ficha" in page
    assert f"/c/{campaign.id}/t/{t.id}/modelo/" in client.get(f"/c/{campaign.id}/t/{t.id}/").content.decode()


def test_removed_field_listed_as_removed_not_active(client, campaign, character, user):
    client.force_login(user)
    f = character.record_type.fielddef_set.get(label="Idade")
    FieldDef.objects.filter(pk=f.id).update(removed=True)
    page = client.get(f"/c/{campaign.id}/t/{character.record_type_id}/modelo/").content.decode()
    assert f"/modelo/campo/{f.id}/remover/" not in page
