import json
import re

import pytest
from django.core.exceptions import ValidationError

from content.render import editor_doc
from indexing.models import Link, SearchEntry
from indexing.services import reindex_record, resolver_for, search
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


def _field_keys(record, kind, n=1):
    return [f.key for f in record.record_type.fielddef_set.filter(kind=kind)[:n]]


def test_field_versions_are_per_key(character):
    k1, k2 = _field_keys(character, "short")[0], _field_keys(character, "long")[0]
    assert save_field(character, k1, "a", 1).version == 2
    r = save_field(character, k2, "b", 1)
    assert r.ok and r.version == 2
    assert save_field(character, k1, "c", 1).ok is False
    character.refresh_from_db()
    assert character.version == 1


def test_bad_bodies_return_400(client, user, text_block, character):
    client.force_login(user)
    url = f"/blocos/{text_block.id}/"
    assert client.post(url, b"[" * 200000, content_type="application/json").status_code == 400
    for bad in ("\ud800", "a\u0000b"):
        body = '{"version": 1, "content": {"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":%s}]}]}}'
        import json as _j
        r = client.post(url, body % _j.dumps(bad), content_type="application/json")
        assert r.status_code == 400, bad
    key = _field_keys(character, "short")[0]
    for bad in ("\ud800", "a\u0000b"):
        r = client.post(f"/r/{character.id}/campos/", _j.dumps({"key": key, "value": bad, "version": 1}),
                        content_type="application/json")
        assert r.status_code == 400, bad


def test_rename_refreshes_embed_label(elf, character):
    from records.save import rename_record
    b = add_embed(tab_of(character), elf, "")
    rename_record(elf, "Elfos Altos")
    elf.delete()
    b.refresh_from_db()
    assert resolve_embed(b).label == "Elfos Altos"


def test_panel_renders_long_field_with_mention(client, user, character, elf):
    client.force_login(user)
    key = _field_keys(character, "long")[0]
    assert save_field(character, key, doc_mention(elf.id, "Elfos"), 1).ok
    html = client.get(f"/r/{character.id}/painel/").content.decode()
    assert f'data-record="{elf.id}"' in html and "'type'" not in html


def _editor_doc(html, doc_id):
    match = re.search(rf'<script id="{doc_id}" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(match.group(1))


def test_block_mount_has_doc_json_and_no_rendered_html_or_form(client, user, character, elf):
    client.force_login(user)
    block = Block.objects.get(tab__record=character, kind="text")
    block.content = doc_mention(elf.id, "Elfos", "visao")
    block.save()
    html = client.get(f"/r/{character.id}/").content.decode()
    mount = re.search(r'<div class="editor" data-editor="text".*?></div>', html, re.S).group(0)
    assert f'data-doc="bloco-{block.id}"' in mount and "<form" not in mount
    assert _editor_doc(html, f"bloco-{block.id}") == block.content
    assert 'class="mention"' not in html
    assert "Remover bloco" in html


def test_editor_doc_uses_current_names_and_lists_deleted(character, elf):
    content = doc_mention(elf.id, "Velho › Visão", "visao")
    content["content"][0]["content"].append(doc_mention(999999, "Sumiu")["content"][0]["content"][0])
    out, missing = editor_doc(content, resolver_for(elf.campaign))
    nodes = out["content"][0]["content"]
    assert nodes[0]["attrs"]["label"] == "Elfos › Visão" and nodes[1]["attrs"]["label"] == "Sumiu"
    assert missing == [999999]
    assert content["content"][0]["content"][0]["attrs"]["label"] == "Velho › Visão"


def test_detail_shows_fields_and_long_field_mount(client, user, character):
    client.force_login(user)
    defs = {f.label: f for f in character.record_type.fielddef_set.all()}
    resumo = defs["Resumo"]
    character.fields = {defs["Ocupação"].key: "Ladino", resumo.key: doc("meio-elfo")}
    character.field_versions = {resumo.key: 7}
    character.save()
    html = client.get(f"/r/{character.id}/").content.decode()
    mount = re.search(r'<div class="editor" data-editor="field".*?></div>', html, re.S).group(0)
    assert "Ladino" in html and "Idade" in html
    assert f'data-key="{resumo.key}"' in mount and 'data-version="7"' in mount
    assert f'data-save-url="/r/{character.id}/campos/"' in mount
    assert _editor_doc(html, f"campo-{resumo.id}") == doc("meio-elfo")


def test_link_field_only_links_safe_addresses(client, user, campaign):
    client.force_login(user)
    track = make_record(campaign, "Trilhas", "Tema")
    key = track.record_type.fielddef_set.get(kind="link").key
    track.fields = {key: "https://exemplo.com/a"}
    track.save()
    assert 'href="https://exemplo.com/a"' in client.get(f"/r/{track.id}/").content.decode()
    track.fields = {key: "javascript:alert(1)"}
    track.save()
    assert 'href="javascript' not in client.get(f"/r/{track.id}/").content.decode()


def test_empty_tab_offers_editor_without_creating_a_block(client, user, campaign):
    client.force_login(user)
    record = make_record(campaign, "Regiões", "Porto")
    tab = record.tab_set.order_by("position", "id").first()
    html = client.get(f"/r/{record.id}/").content.decode()
    assert f'data-create-url="/abas/{tab.id}/blocos/"' in html
    assert not Block.objects.filter(tab=tab).exists()


def _field(record, label):
    return record.record_type.fielddef_set.get(label=label)


@pytest.mark.parametrize("value", ["34", "-2", "1,5", "1.5", ""])
def test_number_field_accepts_numbers_and_clearing(character, value):
    assert save_field(character, _field(character, "Idade").key, value, 1).ok


@pytest.mark.parametrize("value", ["muito", "1 2", "1,", "١٢"])
def test_number_field_refuses_text(client, user, character, value):
    client.force_login(user)
    key = _field(character, "Idade").key
    r = client.post(f"/r/{character.id}/campos/", {"key": key, "value": value, "version": 1},
                    content_type="application/json")
    assert r.status_code == 400 and r.json()["error"] == "Número inválido."
    character.refresh_from_db()
    assert key not in character.fields and key not in character.field_versions


def test_link_field_accepts_safe_addresses_and_clearing(campaign):
    track = make_record(campaign, "Trilhas", "Tema")
    key = _field(track, "Link").key
    assert save_field(track, key, "https://exemplo.com/a", 1).ok
    assert save_field(track, key, "", 2).ok


@pytest.mark.parametrize("value", ["javascript:alert(1)", "exemplo.com", "/relativo"])
def test_link_field_refuses_unsafe_addresses(client, user, campaign, value):
    client.force_login(user)
    track = make_record(campaign, "Trilhas", "Tema")
    r = client.post(f"/r/{track.id}/campos/", {"key": _field(track, "Link").key, "value": value, "version": 1},
                    content_type="application/json")
    assert r.status_code == 400 and r.json()["error"] == "Endereço inválido."


def test_detail_has_editable_inputs_with_version_per_key(client, user, campaign):
    client.force_login(user)
    hero = make_record(campaign, "Personagens", "Kael")
    job, age = _field(hero, "Ocupação"), _field(hero, "Idade")
    hero.fields = {job.key: 'La"dino', age.key: "34"}
    hero.field_versions = {job.key: 3}
    hero.save()
    html = client.get(f"/r/{hero.id}/").content.decode()
    inputs = re.findall(r"<input[^>]*data-field[^>]*>", html)
    assert len(inputs) == 2
    assert f'data-key="{job.key}"' in inputs[0] and 'data-version="3"' in inputs[0]
    assert 'value="La&quot;dino"' in inputs[0]
    assert f'data-save-url="/r/{hero.id}/campos/"' in inputs[0]
    assert 'inputmode="decimal"' in inputs[1] and 'data-version="1"' in inputs[1]


def test_first_text_block_points_to_the_draft_of_its_tab(client, user, character):
    client.force_login(user)
    tab = tab_of(character)
    Block.objects.create(tab=tab, kind="text", position=9, content=doc("segundo"))
    html = client.get(f"/r/{character.id}/").content.decode()
    mounts = re.findall(r'<div class="editor" data-editor="text".*?></div>', html, re.S)
    assert len(mounts) == 2
    assert f'data-orphan-url="/abas/{tab.id}/blocos/"' in mounts[0]
    assert "data-orphan-url" not in mounts[1]


def test_first_block_request_creates_only_when_the_tab_has_none(client, user, campaign):
    client.force_login(user)
    record = make_record(campaign, "Regiões", "Porto")
    tab = tab_of(record)
    url = f"/abas/{tab.id}/blocos/"
    first = client.post(url, {"first": True}, content_type="application/json", headers={"Accept": "application/json"})
    block = Block.objects.get(tab=tab)
    assert first.json() == {"save_url": f"/blocos/{block.id}/", "version": 1}
    assert save_block(block, doc("do pc"), 1).ok
    again = client.post(url, {"first": True}, content_type="application/json", headers={"Accept": "application/json"})
    assert again.json() == {"save_url": f"/blocos/{block.id}/", "version": 2, "content": doc("do pc")}
    assert Block.objects.filter(tab=tab).count() == 1


def test_block_add_answers_json_when_asked(client, user, character):
    client.force_login(user)
    tab = tab_of(character)
    r = client.post(f"/abas/{tab.id}/blocos/", headers={"Accept": "application/json"})
    block = Block.objects.filter(tab=tab, kind="text").order_by("-id").first()
    assert r.json() == {"save_url": f"/blocos/{block.id}/", "version": 1}
