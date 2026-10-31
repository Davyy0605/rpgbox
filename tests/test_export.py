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
