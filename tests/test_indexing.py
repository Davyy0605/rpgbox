import json

import pytest

from campaigns.models import Campaign
from indexing.models import Link
from indexing.normalize import normalize
from indexing.services import (citation_count, citations, reindex_record, resolver_for,
                               search, suggest)
from records.models import Block, Record
from records.services import add_record_tab, create_record

from .helpers import doc, doc_headings, doc_mention


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def other_campaign(user, make_campaign):
    return make_campaign(user, "Outra")


def make_record(campaign, type_name, name, body=None, body_doc=None):
    rtype, _ = campaign.recordtype_set.get_or_create(name=type_name)
    r = create_record(rtype, name)
    if body is not None:
        body_doc = doc(body)
    if body_doc is not None:
        tab = r.tab_set.first() or add_record_tab(r, "Texto")
        Block.objects.create(tab=tab, kind="text", content=body_doc)
    return r


def set_body(record, d):
    Block.objects.filter(tab__record=record).update(content=d)


def test_normalize():
    assert normalize("Cinzênto Ç") == "cinzento c"


def test_accent_insensitive_partial_search(campaign):
    r = make_record(campaign, "Regiões", "Porto Cinzênto"); reindex_record(r)
    assert search(campaign, "cinzen")[0].record == r


def test_name_match_ranks_above_body(campaign):
    a = make_record(campaign, "Personagens", "Dorn", body="fala de kael")
    b = make_record(campaign, "Personagens", "Kael")
    reindex_record(a); reindex_record(b)
    assert search(campaign, "kael")[0].record == b


def test_search_is_scoped_to_campaign(campaign, other_campaign):
    r = make_record(other_campaign, "Personagens", "Kael"); reindex_record(r)
    assert search(campaign, "kael") == []


def test_suggest_includes_heading_with_path(campaign):
    r = make_record(campaign, "Raças", "Elfos", body_doc=doc_headings([(2, "v", "Visão no Escuro")])); reindex_record(r)
    assert {"record": r.id, "anchor": "v", "label": "Elfos › Visão no Escuro"} in suggest(campaign, "visao")


def test_citations_updated_when_mention_removed(campaign):
    k = make_record(campaign, "Personagens", "Kael")
    p = make_record(campaign, "Regiões", "Porto", body_doc=doc_mention(k.id, "Kael")); reindex_record(p)
    assert list(citations(k)) == [p]
    assert citation_count(k) == 1
    set_body(p, doc("nada")); reindex_record(p)
    assert list(citations(k)) == []


def test_mention_to_other_campaign_is_ignored(campaign, other_campaign):
    x = make_record(other_campaign, "Personagens", "X")
    p = make_record(campaign, "Regiões", "P", body_doc=doc_mention(x.id, "X")); reindex_record(p)
    assert Link.objects.filter(source_record=p).count() == 0


def test_empty_query_returns_nothing(campaign):
    assert search(campaign, "   ") == []


def test_embed_block_makes_link_not_body(campaign):
    raca = make_record(campaign, "Raças", "Elfos", body="visao especial")
    p = make_record(campaign, "Personagens", "Kael")
    Block.objects.create(tab=add_record_tab(p, "Raça"), kind="embed", embed_record=raca, embed_anchor="v")
    reindex_record(p); reindex_record(raca)
    link = Link.objects.get(source_record=p)
    assert (link.kind, link.target_record_id, link.target_anchor) == ("embed", raca.id, "v")
    assert citations(raca).get() == p
    assert [x.record for x in search(campaign, "especial")] == [raca]  # embed não entra no corpo de Kael


def test_long_field_is_indexed(campaign):
    t = campaign.recordtype_set.get(name="Personagens")
    key = t.fielddef_set.filter(kind="long").first().key
    r = make_record(campaign, "Personagens", "Mira")
    r.fields = {key: doc("ladra famosa")}; r.save()
    reindex_record(r)
    assert search(campaign, "ladra")[0].record == r


def test_reindex_is_idempotent(campaign):
    k = make_record(campaign, "Personagens", "Kael")
    p = make_record(campaign, "Regiões", "Porto", body_doc=doc_mention(k.id, "Kael"))
    reindex_record(p); reindex_record(p)
    assert Link.objects.filter(source_record=p).count() == 1
    assert len(search(campaign, "porto")) == 1


def test_resolver_for_limits_to_campaign(campaign, other_campaign):
    a = make_record(campaign, "Personagens", "A")
    x = make_record(other_campaign, "Personagens", "X")
    assert resolver_for(campaign)([a.id, x.id]) == {a.id: "A"}


def test_new_record_is_searchable(campaign):
    r = make_record(campaign, "Personagens", "Zéfiro")
    assert search(campaign, "zefiro")[0].record == r


def test_search_view_scoped_and_requires_login(client, user, other_user, campaign):
    make_record(campaign, "Personagens", "Kael")
    assert client.get(f"/c/{campaign.id}/busca/?q=kael").status_code == 302
    client.force_login(other_user)
    assert client.get(f"/c/{campaign.id}/busca/?q=kael").status_code == 404
    client.force_login(user)
    resp = client.get(f"/c/{campaign.id}/busca/?q=kael")
    assert resp.status_code == 200 and "Kael" in resp.content.decode()
    part = client.get(f"/c/{campaign.id}/busca/?q=kael", HTTP_HX_REQUEST="true")
    assert "<html" not in part.content.decode() and "Kael" in part.content.decode()


def test_suggest_view_json(client, user, campaign):
    r = make_record(campaign, "Personagens", "Kael")
    client.force_login(user)
    resp = client.get(f"/c/{campaign.id}/sugestoes/?q=kae")
    assert resp.json() == [{"record": r.id, "anchor": "", "label": "Kael"}]


def test_detail_shows_cited_in_and_home_search_wired(client, user, campaign):
    k = make_record(campaign, "Personagens", "Kael")
    p = make_record(campaign, "Regiões", "Porto", body_doc=doc_mention(k.id, "Kael")); reindex_record(p)
    client.force_login(user)
    html = client.get(f"/r/{k.id}/").content.decode()
    assert "Citado em" in html and "Porto" in html
    assert "Citado em" not in client.get(f"/r/{p.id}/").content.decode()
    assert "Citado em" not in client.get(f"/r/{k.id}/painel/").content.decode()
    home = client.get(f"/c/{campaign.id}/").content.decode()
    assert f'hx-get="/c/{campaign.id}/busca/"' in home and "input changed delay:200ms" in home
