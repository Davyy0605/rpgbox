import pytest
from django.core.exceptions import ValidationError

from indexing.models import Link, SearchEntry
from indexing.services import reindex_record, search
from records.models import Block
from records.save import add_embed, delete_preview, resolve_embed, save_block, save_field

from .helpers import doc, doc_headings, doc_mention
from .test_indexing import make_record, set_body


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def character(campaign):
    return make_record(campaign, "Personagens", "Kael", body="texto")


@pytest.fixture
def elf(campaign):
    return make_record(campaign, "Raças", "Elfos", body="base")


@pytest.fixture
def text_block(character):
    return Block.objects.get(tab__record=character, kind="text")


@pytest.fixture
def foreign_record(user, make_campaign):
    return make_record(make_campaign(user, "Outra"), "Raças", "Anões")


def tab_of(record):
    return record.tab_set.first()


def first_tab(record):
    return record.tab_set.first()


def test_save_increments_version_and_reindexes(text_block):
    assert save_block(text_block, doc("kael"), text_block.version).version == 2
    assert search(text_block.tab.record.campaign, "kael")


def test_stale_version_returns_409_and_keeps_server_text(client, user, text_block):
    client.force_login(user)
    save_block(text_block, doc("do pc"), 1)
    r = client.post(f"/blocos/{text_block.id}/", {"version": 1, "content": doc("do celular")},
                    content_type="application/json")
    assert r.status_code == 409 and r.json()["content"] == doc("do pc")
    text_block.refresh_from_db()
    assert text_block.content == doc("do pc")


def test_save_view_ok_returns_version(client, user, text_block):
    client.force_login(user)
    r = client.post(f"/blocos/{text_block.id}/", {"version": 1, "content": doc("novo")},
                    content_type="application/json")
    assert r.status_code == 200 and r.json()["version"] == 2


def test_invalid_doc_returns_400(client, user, text_block):
    client.force_login(user)
    r = client.post(f"/blocos/{text_block.id}/", {"version": 1, "content": {"type": "iframe"}},
                    content_type="application/json")
    assert r.status_code == 400


def test_bad_json_and_foreign_user_rejected(client, other_user, user, text_block):
    client.force_login(user)
    assert client.post(f"/blocos/{text_block.id}/", "x", content_type="application/json").status_code == 400
    client.force_login(other_user)
    r = client.post(f"/blocos/{text_block.id}/", {"version": 1, "content": doc("x")},
                    content_type="application/json")
    assert r.status_code == 404


def test_empty_text_saves(text_block):
    assert save_block(text_block, doc(""), 1).ok


def test_mention_to_other_campaign_is_harmless(text_block, foreign_record):
    save_block(text_block, doc_mention(foreign_record.id, "Anões"), 1)
    assert not Link.objects.filter(target_record=foreign_record).exists()


def test_embed_shows_current_text_read_only(elf, character):
    b = add_embed(tab_of(character), elf, "")
    set_body(elf, doc("Visão no escuro"))
    assert "Visão no escuro" in resolve_embed(b).html


def test_embed_of_heading_shows_only_section(elf, character):
    set_body(elf, doc_headings([(2, "v", "Visão"), "enxerga", (2, "g", "Graça"), "dança"]))
    html = resolve_embed(add_embed(tab_of(character), elf, "v")).html
    assert "enxerga" in html and "dança" not in html


def test_embed_cycle_stops_at_one_level(campaign):
    a, b = make_record(campaign, "Raças", "A", body="a"), make_record(campaign, "Raças", "B", body="b")
    add_embed(first_tab(a), b, "")
    add_embed(first_tab(b), a, "")
    html = resolve_embed(Block.objects.get(tab=first_tab(a), kind="embed")).html
    assert f'data-record="{a.id}"' in html


def test_embed_cannot_target_own_record(character):
    with pytest.raises(ValidationError):
        add_embed(tab_of(character), character, "")


def test_embed_long_anchor_rejected(elf, character):
    with pytest.raises(ValidationError):
        add_embed(tab_of(character), elf, "a" * 81)
    assert not Block.objects.filter(kind="embed").exists()


def test_embed_of_deleted_record_shows_warning(elf, character):
    b = add_embed(tab_of(character), elf, "")
    elf.delete()
    b.refresh_from_db()
    v = resolve_embed(b)
    assert v.missing and v.label == "Elfos"


def test_embed_other_campaign_404(client, user, character, foreign_record):
    client.force_login(user)
    assert client.post(f"/abas/{tab_of(character).id}/incorporar/",
                       {"record": foreign_record.id}).status_code == 404


def test_embed_add_view_creates_block(client, user, character, elf):
    client.force_login(user)
    r = client.post(f"/abas/{tab_of(character).id}/incorporar/", {"record": elf.id, "anchor": ""})
    assert r.status_code == 302
    assert Block.objects.filter(tab=tab_of(character), kind="embed", embed_record=elf).exists()


def test_delete_preview_counts_citations_and_embeds(elf, character):
    add_embed(tab_of(character), elf, "")
    reindex_record(character)
    assert delete_preview(elf) == 1


def test_rename_updates_mentions_and_search(client, user, character):
    client.force_login(user)
    client.post(f"/r/{character.id}/renomear/", {"name": "Kael II"})
    assert search(character.campaign, "kael ii")[0].record == character


def test_record_delete_asks_then_deletes(client, user, elf, character):
    client.force_login(user)
    add_embed(tab_of(character), elf, "")
    r = client.get(f"/r/{elf.id}/apagar/")
    assert r.status_code == 200 and "1" in r.content.decode()
    client.post(f"/r/{elf.id}/apagar/")
    from records.models import Record
    assert not Record.objects.filter(pk=elf.id).exists()


def test_block_add_and_delete(client, user, character):
    client.force_login(user)
    tab = tab_of(character)
    client.post(f"/abas/{tab.id}/blocos/")
    b = Block.objects.filter(tab=tab, kind="text").order_by("-position").first()
    assert b.position >= 1
    client.post(f"/blocos/{b.id}/apagar/")
    assert not Block.objects.filter(pk=b.id).exists()


def test_save_field_versioning(client, user, character):
    client.force_login(user)
    ftype = character.record_type.fielddef_set.filter(kind="short").first()
    key = ftype.key
    r = client.post(f"/r/{character.id}/campos/", {"key": key, "value": "Elfo", "version": 1},
                    content_type="application/json")
    assert r.status_code == 200 and r.json()["version"] == 2
    r = client.post(f"/r/{character.id}/campos/", {"key": key, "value": "Anão", "version": 1},
                    content_type="application/json")
    assert r.status_code == 409 and r.json()["value"] == "Elfo"
    with pytest.raises(ValidationError):
        save_field(character, "inexistente", "x", 2)


def test_detail_renders_blocks_in_order(client, user, character):
    client.force_login(user)
    tab = tab_of(character)
    Block.objects.filter(tab=tab).delete()
    Block.objects.create(tab=tab, kind="text", position=2, content=doc("segundo"))
    Block.objects.create(tab=tab, kind="text", position=1, content=doc("primeiro"))
    html = client.get(f"/r/{character.id}/").content.decode()
    assert html.index("primeiro") < html.index("segundo")
    assert "data-editor" in html and "data-save-url" in html and "data-suggest-url" in html
    assert "data-version" in html
