import pytest

from transfer.tracks import parse_bulk_tracks


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.mark.parametrize("line,expected", [
    ("Taverna: https://youtu.be/a", ("Taverna", "https://youtu.be/a")),
    ("Duelo | https://x.com/b", ("Duelo", "https://x.com/b")),
    ("https://x.com/c", ("https://x.com/c", "https://x.com/c")),
])
def test_parse_track_line(line, expected):
    assert parse_bulk_tracks(line)[0] == [expected]


def test_parse_reports_bad_lines_and_skips_blank():
    assert parse_bulk_tracks("sem link\n\nA https://x.com/a") == ([("A", "https://x.com/a")], [1])


def test_parse_rejects_unsafe_scheme():
    assert parse_bulk_tracks("x javascript:alert(1)") == ([], [1])


def test_bulk_view_creates_tracks(client, user, campaign):
    rtype = campaign.recordtype_set.get(name="Trilhas")
    client.force_login(user)
    r = client.post(f"/c/{campaign.id}/t/{rtype.id}/trilhas/", {"text": "A: https://x.com/a\nruim\nB | https://x.com/b"})
    assert r.status_code == 200
    key = rtype.fielddef_set.get(kind="link").key
    assert {x.name: x.fields[key] for x in rtype.record_set.all()} == {"A": "https://x.com/a", "B": "https://x.com/b"}
    html = r.content.decode()
    assert "2 trilhas" in html and "Linha 2" in html


def test_bulk_view_404_for_type_without_link(client, user, campaign):
    rtype = campaign.recordtype_set.get(name="Itens")
    client.force_login(user)
    assert client.get(f"/c/{campaign.id}/t/{rtype.id}/trilhas/").status_code == 404


def test_bulk_view_foreign_campaign_404(client, other_user, campaign):
    rtype = campaign.recordtype_set.get(name="Trilhas")
    client.force_login(other_user)
    assert client.get(f"/c/{campaign.id}/t/{rtype.id}/trilhas/").status_code == 404


def test_list_shows_paste_button_only_with_link_field(client, user, campaign):
    client.force_login(user)
    t = campaign.recordtype_set.get(name="Trilhas")
    i = campaign.recordtype_set.get(name="Itens")
    assert "/trilhas/" in client.get(f"/c/{campaign.id}/t/{t.id}/").content.decode()
    assert "/trilhas/" not in client.get(f"/c/{campaign.id}/t/{i.id}/").content.decode()
