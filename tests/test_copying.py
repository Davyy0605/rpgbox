import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from assets.models import Asset
from campaigns.models import FieldDef
from content.doc import iter_nodes, plain_text
from records.models import Block
from transfer.copying import copy_record

from .helpers import doc, doc_headings, doc_mention
from .test_indexing import make_record, set_body
from .test_saving import add_embed, tab_of


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def other_campaign_same_owner(user, make_campaign):
    return make_campaign(user, "Segunda")


@pytest.fixture
def foreign_campaign(other_user, make_campaign):
    return make_campaign(other_user, "Alheia")


@pytest.fixture
def character(campaign):
    return make_record(campaign, "Personagens", "Kael", body="texto")


@pytest.fixture
def elf(campaign):
    return make_record(campaign, "Raças", "Elfos", body="base")


@pytest.fixture
def record_with_image(character, user):
    key = default_storage.save("1/x.webp", ContentFile(b"img"))
    tkey = default_storage.save("1/x_t.webp", ContentFile(b"th"))
    a = Asset.objects.create(owner=user, record=character, tab=tab_of(character), kind="image", filename="x.webp",
                             key=key, thumb_key=tkey, content_type="image/webp", size=5)
    character.main_image = a
    character.save()
    return character


def body_of(record):
    return Block.objects.filter(tab__record=record, kind="text").first().content


def all_text(record):
    return " ".join(plain_text(b.content) for b in Block.objects.filter(tab__record=record, kind="text"))


def test_copy_is_independent(character, other_campaign_same_owner):
    c = copy_record(character, other_campaign_same_owner)
    c.name = "Outro"
    c.save()
    character.refresh_from_db()
    assert character.name == "Kael" and c.campaign == other_campaign_same_owner


def test_copy_carries_fields_and_text(character, other_campaign_same_owner):
    f = FieldDef.objects.get(record_type=character.record_type, label="Ocupação")
    character.fields = {f.key: "Ladino"}
    character.save()
    c = copy_record(character, other_campaign_same_owner)
    assert c.record_type.campaign == other_campaign_same_owner
    nf = c.record_type.fielddef_set.get(label="Ocupação")
    assert c.fields == {nf.key: "Ladino"}
    assert plain_text(body_of(c)) == "texto"


def test_copy_field_without_match_creates_field(character, other_campaign_same_owner):
    f = FieldDef.objects.create(record_type=character.record_type, label="Lema", kind="short")
    character.fields = {f.key: "Vai"}
    character.save()
    c = copy_record(character, other_campaign_same_owner)
    assert c.record_type.fielddef_set.get(label="Lema").key in c.fields


def test_copy_creates_missing_type_from_template(elf, other_campaign_same_owner):
    c = copy_record(elf, other_campaign_same_owner)
    assert c.record_type.name == "Raças" and c.record_type.campaign == other_campaign_same_owner


def test_copy_reuses_existing_type_by_name(character, other_campaign_same_owner):
    existing = other_campaign_same_owner.recordtype_set.get(name="Personagens")
    assert copy_record(character, other_campaign_same_owner).record_type == existing


def test_copy_turns_foreign_mention_into_plain_name(character, elf, other_campaign_same_owner):
    set_body(character, doc_mention(elf.id, "Elfos"))
    body = body_of(copy_record(character, other_campaign_same_owner))
    assert plain_text(body) == "Elfos" and not any(n["type"] == "mention" for n in iter_nodes(body))


def test_copy_freezes_embed_as_editable_text(character, elf, other_campaign_same_owner):
    set_body(elf, doc("Visão"))
    add_embed(tab_of(character), elf, "")
    c = copy_record(character, other_campaign_same_owner)
    assert not Block.objects.filter(tab__record=c, kind="embed").exists()
    assert "Visão" in all_text(c)


def test_copy_freezes_only_anchored_section(character, elf, other_campaign_same_owner):
    set_body(elf, doc_headings((2, "a", "Visão"), "dentro", (2, "b", "Outro"), "fora"))
    add_embed(tab_of(character), elf, "a")
    c = copy_record(character, other_campaign_same_owner)
    text = all_text(c)
    assert "dentro" in text and "fora" not in text


def test_copy_duplicates_files_independently(record_with_image, other_campaign_same_owner):
    c = copy_record(record_with_image, other_campaign_same_owner)
    a = c.asset_set.get()
    old = record_with_image.asset_set.get().key
    assert a.key != old and default_storage.exists(a.key) and default_storage.exists(a.thumb_key)
    assert c.main_image == a and a.tab.record == c


def test_copy_view_to_other_campaign(client, user, character, other_campaign_same_owner):
    client.force_login(user)
    r = client.post(f"/r/{character.id}/copiar/", {"campaign": other_campaign_same_owner.id})
    assert r.status_code == 302
    assert other_campaign_same_owner.recordtype_set.get(name="Personagens").record_set.get().name == "Kael"
    assert client.get(f"/r/{character.id}/copiar/").status_code == 200


def test_copy_to_other_masters_campaign_404(client, user, character, foreign_campaign):
    client.force_login(user)
    assert client.post(f"/r/{character.id}/copiar/", {"campaign": foreign_campaign.id}).status_code == 404


def test_copy_to_same_campaign_404(client, user, character, campaign):
    client.force_login(user)
    assert client.post(f"/r/{character.id}/copiar/", {"campaign": campaign.id}).status_code == 404


def test_copy_same_label_fields_keep_both_values(character, other_campaign_same_owner):
    a = FieldDef.objects.create(record_type=character.record_type, label="Lema", kind="short")
    b = FieldDef.objects.create(record_type=character.record_type, label="Lema", kind="short")
    character.fields = {a.key: "um", b.key: "dois"}
    character.save()
    c = copy_record(character, other_campaign_same_owner)
    assert sorted(c.fields.values()) == ["dois", "um"]
    c2 = copy_record(character, other_campaign_same_owner)
    assert sorted(c2.fields.values()) == ["dois", "um"]


def test_copy_same_label_other_kind_gets_new_field(character, other_campaign_same_owner):
    dest_type = other_campaign_same_owner.recordtype_set.get(name="Personagens")
    FieldDef.objects.create(record_type=dest_type, label="Lema", kind="number")
    f = FieldDef.objects.create(record_type=character.record_type, label="Lema", kind="short")
    character.fields = {f.key: "texto"}
    character.save()
    c = copy_record(character, other_campaign_same_owner)
    nf = dest_type.fielddef_set.get(label="Lema", kind="short")
    assert c.fields == {nf.key: "texto"} and dest_type.fielddef_set.filter(label="Lema").count() == 2


def test_copy_failure_leaves_nothing_and_removes_files(record_with_image, other_campaign_same_owner, user, monkeypatch):
    from campaigns.models import RecordType
    from records.models import Record, Tab

    key = default_storage.save("1/y.webp", ContentFile(b"img2"))
    tkey = default_storage.save("1/y_t.webp", ContentFile(b"th2"))
    Asset.objects.create(owner=user, record=record_with_image, kind="image", filename="y.webp", key=key,
                         thumb_key=tkey, content_type="image/webp", size=4)
    real_save, saved = default_storage.save, []

    def flaky(name, content, *a, **kw):
        if len(saved) == 3:
            raise OSError("falha")
        k = real_save(name, content, *a, **kw)
        saved.append(k)
        return k

    monkeypatch.setattr(default_storage, "save", flaky)
    types_before = RecordType.objects.filter(campaign=other_campaign_same_owner).count()
    with pytest.raises(OSError):
        copy_record(record_with_image, other_campaign_same_owner)
    assert len(saved) == 3
    assert not any(default_storage.exists(k) for k in saved)
    assert not Record.objects.filter(campaign=other_campaign_same_owner).exists()
    assert not Tab.objects.filter(record__campaign=other_campaign_same_owner).exists()
    assert Asset.objects.count() == 2
    assert RecordType.objects.filter(campaign=other_campaign_same_owner).count() == types_before
