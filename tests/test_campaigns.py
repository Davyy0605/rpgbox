from campaigns.defaults import seed_campaign
from campaigns.models import Campaign


def test_new_campaign_gets_default_types(user):
    c = Campaign.objects.create(owner=user, name="Vael"); seed_campaign(c)
    assert list(c.recordtype_set.order_by("position").values_list("name", flat=True)) == ["Personagens", "Itens", "Regiões", "Trilhas"]


def test_default_character_template(user, make_campaign):
    c = make_campaign(user)
    t = c.recordtype_set.get(name="Personagens")
    assert [f.label for f in t.fielddef_set.order_by("position")] == ["Ocupação", "Idade", "Resumo"]
    assert [x.title for x in t.tabdef_set.order_by("position")] == ["Ficha", "Habilidades", "Magias", "História"]


def test_track_template_has_link_field_and_no_tabs(user, make_campaign):
    t = make_campaign(user).recordtype_set.get(name="Trilhas")
    assert t.fielddef_set.filter(label="Link", kind="link").exists() and not t.tabdef_set.exists()


def test_other_user_gets_404(client, user, other_user, make_campaign):
    c = make_campaign(user); client.force_login(other_user)
    assert client.get(f"/c/{c.id}/").status_code == 404


def test_root_opens_last_campaign(client, user, make_campaign):
    c = make_campaign(user); client.force_login(user); client.get(f"/c/{c.id}/")
    assert client.get("/").url == f"/c/{c.id}/"


def test_root_without_campaign_goes_to_list(client, user):
    client.force_login(user)
    assert client.get("/").url == "/c/"


def test_create_campaign_seeds_types(client, user):
    client.force_login(user)
    r = client.post("/c/", {"name": "Nova"})
    c = Campaign.objects.get(name="Nova")
    assert r.url == f"/c/{c.id}/" and c.recordtype_set.count() == 4
