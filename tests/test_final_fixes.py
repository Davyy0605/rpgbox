"""Correções da revisão final (I1-I6, M1-M4)."""
import io
import os
import subprocess
import sys

import pytest
from django.conf import settings
from PIL import Image

from assets.images import process_image
from assets.models import Asset
from content.render import render_doc
from records.services import create_record, visible_tabs
from transfer.copying import copy_record

from .helpers import doc, doc_mention
from .test_copying import body_of
from .test_export import export, make_record, text_block
from .test_indexing import make_record as make_indexed, set_body


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


def test_export_long_field_is_markdown_not_dict_repr(campaign):
    r = make_record(campaign, "Personagens", "Kael")
    f = r.record_type.fielddef_set.get(kind="long")
    r.fields[f.key] = doc("Nasceu na torre")
    r.save()
    md = export(campaign).read("Personagens/Kael/registro.md").decode()
    assert "Nasceu na torre" in md and "'type'" not in md


def test_export_keeps_removed_field_with_content(campaign):
    r = make_record(campaign, "Personagens", "Kael")
    f = r.record_type.fielddef_set.get(label="Ocupação")
    r.fields[f.key] = "Ladino"
    r.save()
    f.removed = True
    f.save()
    assert "Ladino" in export(campaign).read("Personagens/Kael/registro.md").decode()


def test_export_uses_current_mention_name(campaign):
    a = make_record(campaign, "Raças", "Elfos")
    b = make_record(campaign, "Personagens", "Kael")
    text_block(b, doc_mention(a.id, "Elfos"))
    a.name = "Elfos Altos"
    a.save()
    assert "Elfos Altos" in export(campaign).read("Personagens/Kael/registro.md").decode()


def test_copy_uses_current_mention_name(campaign, user, make_campaign):
    a = make_record(campaign, "Raças", "Elfos")
    b = make_indexed(campaign, "Personagens", "Kael", body="x")
    set_body(b, doc_mention(a.id, "Elfos"))
    a.name = "Elfos Altos"
    a.save()
    body = body_of(copy_record(b, make_campaign(user, "Segunda")))
    assert body["content"][0]["content"][0]["text"] == "Elfos Altos"


def test_removed_tab_with_only_files_stays_visible(campaign):
    rec = create_record(campaign.recordtype_set.get(name="Personagens"), "Kael")
    tab = visible_tabs(rec)[0]
    Asset.objects.create(owner=campaign.owner, record=rec, tab=tab, kind="file", filename="a.txt",
                         key="1/a.txt", content_type="text/plain", size=1)
    tab.tab_def.removed = True
    tab.tab_def.save()
    assert tab.title in [t.title for t in visible_tabs(rec)]


def _track(campaign, link):
    rec = create_record(campaign.recordtype_set.get(name="Trilhas"), "Taberna")
    rec.fields[rec.record_type.fielddef_set.get(kind="link").key] = link
    rec.save()
    return rec


def test_panel_has_copy_button_for_link_field(client, user, campaign):
    rec = _track(campaign, "https://exemplo.com/musica")
    client.force_login(user)
    assert 'data-copy="https://exemplo.com/musica"' in client.get(f"/r/{rec.id}/painel/").content.decode()


def test_panel_has_no_copy_button_for_unsafe_link(client, user, campaign):
    rec = _track(campaign, "javascript:alert(1)")
    client.force_login(user)
    assert "data-copy" not in client.get(f"/r/{rec.id}/painel/").content.decode()


def test_mention_to_heading_shows_record_and_heading():
    html = render_doc(doc_mention(5, "Velho › Visão no Escuro", anchor="visao"), lambda ids: {5: "Elfos"})
    assert "Elfos › Visão no Escuro</a>" in html


def test_mpo_jpeg_gets_jpeg_draft_mode(monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buf, "JPEG")
    real, calls = Image.open, []

    def fake_open(f, **kw):
        im = real(f, **kw)
        im.format = "MPO"  # iPhone com mapa de ganho: o Pillow abre como MPO
        monkeypatch.setattr(im, "draft", lambda *a: calls.append(a))
        return im
    monkeypatch.setattr(Image, "open", fake_open)
    process_image(buf)
    assert calls


def test_campaign_list_has_logout_form(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("ana", "a@x.com", "x"))
    html = client.get("/c/").content.decode()
    assert 'action="/sair"' in html and "Sair" in html
    assert client.post("/sair").status_code == 302
    assert "_auth_user_id" not in client.session


def test_delete_buttons_ask_for_confirmation(client, user, campaign):
    rec = make_indexed(campaign, "Personagens", "Kael", body="oi")
    tab = rec.tab_set.first()
    for kind, name in (("image", "a.webp"), ("file", "b.txt")):
        Asset.objects.create(owner=user, record=rec, tab=None, kind=kind, filename=name, key="1/" + name,
                             content_type="x/y", size=1)
    client.force_login(user)
    assert "Remover bloco</summary>" in client.get(f"/r/{rec.id}/?aba={tab.id}").content.decode()
    assert client.get(f"/r/{rec.id}/?aba=galeria").content.decode().count("Excluir</summary>") == 2


def test_production_requires_database_and_bucket():
    base = {k: v for k, v in os.environ.items() if k not in ("DEBUG", "DATABASE_URL", "R2_BUCKET")}
    base["SECRET_KEY"] = "x"

    def run(**extra):
        return subprocess.run([sys.executable, "-c", "import config.settings"], env={**base, **extra},
                              capture_output=True, text=True)
    assert run(R2_BUCKET="b").returncode != 0
    assert run(DATABASE_URL="sqlite:///x.db").returncode != 0
    assert run(DATABASE_URL="sqlite:///x.db", R2_BUCKET="b").returncode == 0


def test_upload_shows_visible_busy_text():
    css = (settings.BASE_DIR / "static/css/app.css").read_text(encoding="utf8")
    assert '[data-dropzone][aria-busy=true]::after { content: "Enviando..."' in css
