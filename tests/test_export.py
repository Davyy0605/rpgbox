import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from assets.storage import store_upload
from records.models import Tab
from records.save import add_embed, add_text_block
from records.services import create_record
from tests.helpers import doc
from transfer.export import write_export


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


def make_record(campaign, type_name, name):
    rt, _ = campaign.recordtype_set.get_or_create(name=type_name)
    return create_record(rt, name)


def export(campaign):
    buf = io.BytesIO()
    write_export(campaign, buf)
    return zipfile.ZipFile(buf)


def first_tab(record):
    return record.tab_set.first() or Tab.objects.create(record=record, title="Geral")


def text_block(record, content):
    b = add_text_block(first_tab(record))
    b.content = content
    b.save()
    return b


def test_export_has_text_and_files(campaign):
    r = make_record(campaign, "Personagens", "Kael")
    text_block(r, doc("Olá mundo"))
    store_upload(r, None, SimpleUploadedFile("nota.txt", b"hello", content_type="text/plain"))
    z = export(campaign)
    names = z.namelist()
    assert any(n.endswith("registro.md") for n in names) and any("/arquivos/" in n for n in names)
    md = z.read("Personagens/Kael/registro.md").decode()
    assert "Olá mundo" in md and "# Kael" in md
    assert z.read("Personagens/Kael/arquivos/nota.txt") == b"hello"


def test_export_handles_unsafe_and_duplicate_names(campaign):
    make_record(campaign, "Itens", "a/../b")
    make_record(campaign, "Itens", "a/../b")
    names = export(campaign).namelist()
    assert not any(".." in n for n in names) and len(set(names)) == len(names) == 2


def test_export_embed_as_current_text(campaign):
    a = make_record(campaign, "Locais", "Torre")
    text_block(a, doc("Texto atual"))
    b = make_record(campaign, "Locais", "Mapa")
    add_embed(first_tab(b), a, "")
    md = export(campaign).read("Locais/Mapa/registro.md").decode()
    assert "Texto atual" in md


def test_export_view_is_owner_only(client, user, other_user, campaign):
    url = reverse("campaign-export", args=[campaign.id])
    client.force_login(other_user)
    assert client.get(url).status_code == 404
    client.force_login(user)
    r = client.get(url)
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    assert zipfile.is_zipfile(io.BytesIO(b"".join(r.streaming_content)))


def test_missing_storage_key_is_reported_not_swallowed(campaign, caplog):
    from assets.models import Asset
    r = make_record(campaign, "Personagens", "Kael")
    store_upload(r, None, SimpleUploadedFile("ok.txt", b"ok", content_type="text/plain"))
    a = store_upload(r, None, SimpleUploadedFile("sumiu.txt", b"x", content_type="text/plain"))
    Asset.objects.filter(pk=a.pk).update(key="nao/existe.txt")
    z = export(campaign)
    assert z.testzip() is None
    assert "Personagens/Kael/arquivos/ok.txt" in z.namelist()
    assert not any(n.endswith("sumiu.txt") for n in z.namelist())
    assert "sumiu.txt" in z.read("erros.txt").decode()
    assert "Falha ao exportar" in caplog.text


def test_no_erros_file_when_all_ok(campaign):
    make_record(campaign, "Personagens", "Kael")
    assert "erros.txt" not in export(campaign).namelist()


def test_export_basic_fields(campaign):
    from campaigns.models import FieldDef
    r = make_record(campaign, "Personagens", "Kael")
    fd = FieldDef.objects.create(record_type=r.record_type, label="Classe", kind="short", position=99)
    r.fields = {fd.key: "Mago"}
    r.save()
    assert "**Classe:** Mago" in export(campaign).read("Personagens/Kael/registro.md").decode()


def test_export_subtab(campaign):
    r = make_record(campaign, "Personagens", "Kael")
    parent = Tab.objects.create(record=r, title="Historia", position=50)
    sub = Tab.objects.create(record=r, title="Infancia", parent=parent, position=51)
    b = add_text_block(sub)
    b.content = doc("Nasceu longe")
    b.save()
    md = export(campaign).read("Personagens/Kael/registro.md").decode()
    assert "## Historia" in md and "### Infancia" in md and "Nasceu longe" in md
    assert md.index("## Historia") < md.index("### Infancia") < md.index("Nasceu longe")


def test_export_embed_with_anchor(campaign):
    from tests.helpers import doc_headings
    a = make_record(campaign, "Locais", "Torre")
    text_block(a, doc_headings((2, "sec-a", "Secao A"), "texto da A", (2, "sec-b", "Secao B"), "texto da B"))
    b = make_record(campaign, "Locais", "Mapa")
    add_embed(first_tab(b), a, "sec-b")
    md = export(campaign).read("Locais/Mapa/registro.md").decode()
    assert "texto da B" in md and "texto da A" not in md


def test_export_removed_embed_target(campaign):
    a = make_record(campaign, "Locais", "Torre")
    b = make_record(campaign, "Locais", "Mapa")
    add_embed(first_tab(b), a, "")
    a.delete()
    md = export(campaign).read("Locais/Mapa/registro.md").decode()
    assert "Torre" in md and "removido" in md


def test_export_tab_file_and_duplicate_filenames(campaign):
    r = make_record(campaign, "Personagens", "Kael")
    tab = first_tab(r)
    store_upload(r, tab, SimpleUploadedFile("mapa.txt", b"1", content_type="text/plain"))
    store_upload(r, None, SimpleUploadedFile("mapa.txt", b"2", content_type="text/plain"))
    z = export(campaign)
    files = sorted(n for n in z.namelist() if "/arquivos/" in n)
    assert files == ["Personagens/Kael/arquivos/mapa (2).txt", "Personagens/Kael/arquivos/mapa.txt"]
    assert {z.read(n) for n in files} == {b"1", b"2"}
