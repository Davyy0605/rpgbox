import io
import zipfile

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from assets.models import Asset
from assets.storage import store_upload
from campaigns.models import Campaign, ListGroup, RecordType, TabDef
from indexing.models import Link, SearchEntry
from indexing.services import citations, reindex_record, search
from records.models import Block, Record, Tab
from records.save import resolve_embed
from records.services import add_record_tab, add_subtab, create_record, visible_tabs
from transfer.copying import copy_record
from transfer.export import write_export

from .helpers import doc, doc_mention
from .test_indexing import make_record

JSON = {"HTTP_ACCEPT": "application/json"}
HTMX = {"HTTP_HX_REQUEST": "true"}


def stored_png(record, tab=None):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 200, 30)).save(buf, "PNG")
    return store_upload(record, tab, SimpleUploadedFile("a.png", buf.getvalue(), "image/png"))


def gone_from_storage(asset):
    return not default_storage.exists(asset.key) and not default_storage.exists(asset.thumb_key)


@pytest.fixture
def signed_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def kael(campaign):
    return make_record(campaign, "Personagens", "Kael", body="texto")


@pytest.fixture
def template_tab(kael):
    """Kael e outro registro do mesmo tipo têm a aba `Segredos`, vinda do modelo."""
    TabDef.objects.create(record_type=kael.record_type, title="Segredos", position=50)
    visible_tabs(kael)
    return kael.tab_set.get(title="Segredos")


def titles(record):
    return [t.title for t in visible_tabs(record)]


def post_delete(client, url, **headers):
    return client.post(url, **{**JSON, **headers})


# Abas


def test_tab_made_in_the_record_goes_with_blocks_and_files(signed_in, kael, django_capture_on_commit_callbacks):
    tab = add_record_tab(kael, "Notas")
    sub = add_subtab(tab, "Sub")
    Block.objects.create(tab=sub, kind="text", content=doc("x"))
    assets = [stored_png(kael, tab), stored_png(kael, sub)]
    with django_capture_on_commit_callbacks(execute=True):
        r = post_delete(signed_in, f"/abas/{tab.id}/apagar/")
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert not Tab.objects.filter(pk__in=[tab.pk, sub.pk]).exists()
    assert not Block.objects.filter(tab_id__in=[tab.pk, sub.pk]).exists()
    assert not Asset.objects.filter(record=kael).exists() and all(gone_from_storage(a) for a in assets)


def test_template_tab_stays_gone_from_this_record_only(signed_in, kael, template_tab, django_capture_on_commit_callbacks):
    other = create_record(kael.record_type, "Mira")
    Block.objects.create(tab=template_tab, kind="text", content=doc("segredo"))
    Block.objects.create(tab=other.tab_set.get(title="Segredos"), kind="text", content=doc("dela"))
    asset = stored_png(kael, template_tab)
    with django_capture_on_commit_callbacks(execute=True):
        post_delete(signed_in, f"/abas/{template_tab.id}/apagar/")
    assert "Segredos" not in titles(kael)
    assert "Segredos" not in titles(kael)  # a segunda sincronização também não traz de volta
    assert kael.tab_set.filter(title="Segredos").count() == 1
    assert not Block.objects.filter(tab=template_tab).exists() and gone_from_storage(asset)
    assert "Segredos" in titles(other) and Block.objects.filter(tab__record=other, content=doc("dela")).exists()


def test_subtabs_of_a_hidden_template_tab_go_too(signed_in, kael, template_tab):
    from_template = TabDef.objects.create(record_type=kael.record_type, parent=template_tab.tab_def, title="Filha", position=51)
    visible_tabs(kael)
    made_here = add_subtab(template_tab, "Minha")
    post_delete(signed_in, f"/abas/{template_tab.id}/apagar/")
    assert not Tab.objects.filter(pk=made_here.pk).exists()
    assert kael.tab_set.get(tab_def=from_template).hidden
    assert all(t.title != "Filha" for top in visible_tabs(kael) for t in [top, *top.children])


def test_template_subtab_alone_can_be_hidden(signed_in, kael, template_tab):
    sub_def = TabDef.objects.create(record_type=kael.record_type, parent=template_tab.tab_def, title="Filha", position=51)
    visible_tabs(kael)
    post_delete(signed_in, f"/abas/{kael.tab_set.get(tab_def=sub_def).id}/apagar/")
    top = next(t for t in visible_tabs(kael) if t.title == "Segredos")
    assert top.children == []


def test_new_template_subtab_under_a_hidden_tab_does_not_appear(signed_in, kael, template_tab):
    post_delete(signed_in, f"/abas/{template_tab.id}/apagar/")
    TabDef.objects.create(record_type=kael.record_type, parent=template_tab.tab_def, title="Tardia", position=52)
    assert all(t.title != "Tardia" for top in visible_tabs(kael) for t in [top, *top.children])


def test_hidden_tab_refuses_new_content(signed_in, kael, template_tab):
    post_delete(signed_in, f"/abas/{template_tab.id}/apagar/")
    assert signed_in.post(f"/abas/{template_tab.id}/blocos/").status_code == 404
    assert signed_in.post(f"/abas/{template_tab.id}/apagar/").status_code == 404
    assert signed_in.post(f"/r/{kael.id}/abas/{template_tab.id}/sub/", {"title": "x"}).status_code == 404
    assert signed_in.post(f"/r/{kael.id}/arquivos/", {"tab": template_tab.id}).status_code == 404


def test_deleting_the_open_tab_falls_back_to_a_visible_one(signed_in, kael):
    tab = add_record_tab(kael, "Notas")
    r = signed_in.post(f"/abas/{tab.id}/apagar/")
    assert r.status_code == 302 and r.url == f"/r/{kael.id}/"
    page = signed_in.get(f"/r/{kael.id}/?aba={tab.id}")
    assert page.status_code == 200 and page.context["selected"] is not None


def test_record_without_tabs_left_still_opens(signed_in, kael):
    for tab in visible_tabs(kael):
        post_delete(signed_in, f"/abas/{tab.id}/apagar/")
    page = signed_in.get(f"/r/{kael.id}/")
    assert page.status_code == 200 and "não tem abas" in page.content.decode()


def test_deleting_a_tab_reindexes_search_and_citations(signed_in, campaign, kael):
    elf = make_record(campaign, "Raças", "Elfos")
    tab = add_record_tab(kael, "Notas")
    Block.objects.create(tab=tab, kind="text", content=doc_mention(elf.id, "Elfos"))
    Block.objects.create(tab=tab, kind="text", content=doc("palavradiferente"))
    reindex_record(kael)
    assert search(campaign, "palavradiferente") and list(citations(elf)) == [kael]
    post_delete(signed_in, f"/abas/{tab.id}/apagar/")
    assert not search(campaign, "palavradiferente") and not citations(elf).exists()


def test_hidden_tab_stays_out_of_export_and_copy(signed_in, user, make_campaign, campaign, kael, template_tab):
    post_delete(signed_in, f"/abas/{template_tab.id}/apagar/")
    buf = io.BytesIO()
    write_export(campaign, buf)
    assert "Segredos" not in zipfile.ZipFile(buf).read("Personagens/Kael/registro.md").decode()
    dest = make_campaign(user, "Destino")
    TabDef.objects.create(record_type=dest.recordtype_set.get(name="Personagens"), title="Segredos")
    assert "Segredos" not in titles(copy_record(kael, dest))


# Tipo e campanha


def test_type_goes_with_everything_in_it(signed_in, campaign, kael, django_capture_on_commit_callbacks):
    asset = stored_png(kael)
    rtype = kael.record_type
    with django_capture_on_commit_callbacks(execute=True):
        r = post_delete(signed_in, f"/c/{campaign.id}/t/{rtype.id}/apagar/")
    assert r.json() == {"deleted": True}
    assert not RecordType.objects.filter(pk=rtype.pk).exists() and not Record.objects.filter(pk=kael.pk).exists()
    assert not SearchEntry.objects.filter(record_id=kael.pk).exists() and gone_from_storage(asset)


def test_deleted_type_leaves_struck_mentions_and_embeds_elsewhere(signed_in, campaign, kael):
    elf = make_record(campaign, "Raças", "Elfos", body_doc=doc_mention(kael.id, "Kael"))
    reindex_record(elf)
    embed = Block.objects.create(tab=elf.tab_set.first(), kind="embed", embed_record=kael, embed_label="Kael")
    signed_in.post(f"/c/{campaign.id}/t/{kael.record_type_id}/apagar/")
    embed.refresh_from_db()
    assert resolve_embed(embed).missing and resolve_embed(embed).label == "Kael"
    assert not Link.objects.filter(source_record=elf).exists()
    assert signed_in.get(f"/r/{elf.id}/").status_code == 200


def test_campaign_goes_with_everything_in_it(signed_in, campaign, kael, django_capture_on_commit_callbacks):
    asset = stored_png(kael)
    with django_capture_on_commit_callbacks(execute=True):
        r = post_delete(signed_in, f"/c/{campaign.id}/apagar/")
    assert r.json() == {"deleted": True}
    assert not Campaign.objects.filter(pk=campaign.pk).exists() and not Asset.objects.exists()
    assert gone_from_storage(asset)
    assert signed_in.get("/").status_code == 302


@pytest.mark.parametrize("url,back", [
    ("/c/{c}/apagar/", "/c/"),
    ("/c/{c}/t/{t}/apagar/", "/c/{c}/"),
])
def test_without_js_deleting_goes_to_the_screen_above(signed_in, campaign, kael, url, back):
    ids = {"c": campaign.id, "t": kael.record_type_id}
    r = signed_in.post(url.format(**ids))
    assert r.status_code == 302 and r.url == back.format(**ids)


# Registro, sub-aba da lista e arquivo pelo menu


def test_record_by_menu_answers_json_and_cleans_storage(signed_in, kael, django_capture_on_commit_callbacks):
    asset = stored_png(kael)
    with django_capture_on_commit_callbacks(execute=True):
        assert post_delete(signed_in, f"/r/{kael.id}/apagar/").json() == {"deleted": True}
    assert not Record.objects.filter(pk=kael.pk).exists() and gone_from_storage(asset)


def test_list_group_by_menu_keeps_its_records(signed_in, kael):
    group = ListGroup.objects.create(record_type=kael.record_type, name="G")
    kael.group = group
    kael.save()
    assert post_delete(signed_in, f"/modelo/grupo/{group.id}/remover/").json() == {"deleted": True}
    kael.refresh_from_db()
    assert kael.group is None


def test_asset_by_menu_answers_json(signed_in, kael, django_capture_on_commit_callbacks):
    asset = stored_png(kael)
    with django_capture_on_commit_callbacks(execute=True):
        assert post_delete(signed_in, f"/arquivos/{asset.id}/excluir/").json() == {"deleted": True}
    assert gone_from_storage(asset)


def test_storage_failure_does_not_undo_or_break_the_answer(signed_in, kael, monkeypatch, caplog, django_capture_on_commit_callbacks):
    asset = stored_png(kael, add_record_tab(kael, "Notas"))

    def broken(key):
        raise OSError("sem armazenamento")

    monkeypatch.setattr(default_storage, "delete", broken)
    with django_capture_on_commit_callbacks(execute=True):
        r = post_delete(signed_in, f"/abas/{asset.tab_id}/apagar/")
    assert r.json() == {"deleted": True} and not Asset.objects.filter(pk=asset.pk).exists()
    assert "Falha ao remover objeto" in caplog.text


@pytest.mark.parametrize("url", ["/c/{c}/apagar/", "/c/{c}/t/{t}/apagar/", "/abas/{tab}/apagar/"])
def test_new_routes_refuse_get(signed_in, campaign, kael, url):
    assert signed_in.get(url.format(c=campaign.id, t=kael.record_type_id, tab=kael.tab_set.first().id)).status_code == 405


@pytest.mark.parametrize("url", ["/c/{c}/apagar/", "/c/{c}/t/{t}/apagar/", "/abas/{tab}/apagar/"])
def test_new_routes_need_login(client, campaign, kael, url):
    r = client.post(url.format(c=campaign.id, t=kael.record_type_id, tab=kael.tab_set.first().id))
    assert r.status_code == 302 and "/entrar" in r.url and Campaign.objects.filter(pk=campaign.pk).exists()


# Respostas com e sem htmx


def test_personalizar_answers_the_fragment_directly_with_htmx(signed_in, kael):
    rtype = kael.record_type
    r = signed_in.post(f"/modelo/tipo/{rtype.id}/campo/", {"label": "Altura", "kind": "short"}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "Altura" in html and "<html" not in html and 'id="modelo"' not in html


def test_personalizar_still_redirects_without_htmx(signed_in, kael):
    rtype = kael.record_type
    r = signed_in.post(f"/modelo/tipo/{rtype.id}/campo/", {"label": "Altura", "kind": "short"})
    assert r.status_code == 302 and r.url == f"/c/{rtype.campaign_id}/t/{rtype.id}/modelo/"


@pytest.mark.parametrize("action", ["rename", "move", "remove"])
def test_every_field_action_answers_the_fragment(signed_in, kael, action):
    field = kael.record_type.fielddef_set.first()
    url = {"rename": "renomear", "move": "mover", "remove": "remover"}[action]
    r = signed_in.post(f"/modelo/campo/{field.id}/{url}/", {"label": "Novo", "dir": "down"}, **HTMX)
    assert r.status_code == 200 and "<html" not in r.content.decode() and "<h2>Campos</h2>" in r.content.decode()


@pytest.mark.parametrize("action", ["renomear", "mover", "remover"])
def test_every_tabdef_action_answers_the_fragment(signed_in, kael, action):
    tabdef = TabDef.objects.create(record_type=kael.record_type, title="Aba", position=60)
    r = signed_in.post(f"/modelo/aba/{tabdef.id}/{action}/", {"title": "Nova", "dir": "up"}, **HTMX)
    assert r.status_code == 200 and "<h2>Abas</h2>" in r.content.decode()


def test_group_add_from_personalizar_answers_personalizar(signed_in, campaign, kael):
    url = f"/c/{campaign.id}/t/{kael.record_type_id}/grupos/novo/"
    r = signed_in.post(url, {"name": "Taverna"}, HTTP_HX_TARGET="modelo", **HTMX)
    assert r.status_code == 200 and "<h2>Sub-abas da lista</h2>" in r.content.decode()


def test_group_rename_and_remove_answer_personalizar(signed_in, kael):
    group = ListGroup.objects.create(record_type=kael.record_type, name="G")
    assert "Taverna" in signed_in.post(f"/modelo/grupo/{group.id}/renomear/", {"name": "Taverna"}, **HTMX).content.decode()
    assert "Taverna" not in signed_in.post(f"/modelo/grupo/{group.id}/remover/", **HTMX).content.decode()


def test_group_add_from_the_list_answers_the_strip_in_the_same_filter(signed_in, campaign, kael):
    old = ListGroup.objects.create(record_type=kael.record_type, name="Velha")
    url = f"/c/{campaign.id}/t/{kael.record_type_id}/grupos/novo/"
    r = signed_in.post(url, {"name": "Nova", "g": old.id, "v": "galeria"}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "<html" not in html and "Nova" in html and "autofocus" in html
    assert r.context["current_group"] == old and r.context["gallery"]


def test_tab_add_answers_the_strip_and_keeps_the_open_tab(signed_in, kael):
    open_tab = visible_tabs(kael)[0]
    r = signed_in.post(f"/r/{kael.id}/abas/nova/", {"title": "Nova", "aba": open_tab.id}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "<html" not in html and "Nova" in html and "autofocus" in html
    assert r.context["selected"] == open_tab


def test_subtab_add_answers_the_strip(signed_in, kael):
    open_tab = visible_tabs(kael)[0]
    r = signed_in.post(f"/r/{kael.id}/abas/{open_tab.id}/sub/", {"title": "Filha", "aba": open_tab.id}, **HTMX)
    assert r.status_code == 200 and "Filha" in r.content.decode() and 'aria-label="Sub-abas"' in r.content.decode()


def test_tab_add_from_the_gallery_keeps_the_gallery(signed_in, kael):
    r = signed_in.post(f"/r/{kael.id}/abas/nova/", {"title": "Nova", "aba": "galeria"}, **HTMX)
    assert r.context["gallery"] and r.context["selected"] is None


def test_first_tab_of_an_empty_record_reloads_into_it(signed_in, kael):
    Tab.objects.filter(record=kael).delete()
    r = signed_in.post(f"/r/{kael.id}/abas/nova/", {"title": "Nova", "aba": ""}, **HTMX)
    assert r.headers["HX-Redirect"] == f"/r/{kael.id}/?aba={kael.tab_set.get().id}"


def test_tab_add_still_redirects_without_htmx(signed_in, kael):
    r = signed_in.post(f"/r/{kael.id}/abas/nova/", {"title": "Nova"})
    assert r.status_code == 302 and r.url == f"/r/{kael.id}/?aba={kael.tab_set.get(title='Nova').id}"


def test_block_add_answers_only_the_new_block(signed_in, kael):
    tab = kael.tab_set.first()
    r = signed_in.post(f"/abas/{tab.id}/blocos/", **HTMX)
    block = tab.block_set.order_by("-id").first()
    html = r.content.decode()
    assert r.status_code == 200 and f"bloco-{block.id}" in html and "<html" not in html
    assert html.count("data-editor") == 1


def test_embed_add_answers_only_the_new_block(signed_in, campaign, kael):
    elf = make_record(campaign, "Raças", "Elfos", body="base")
    r = signed_in.post(f"/abas/{kael.tab_set.first().id}/incorporar/", {"record": elf.id}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "base" in html and "<html" not in html and html.count("embed-block") == 1


def test_block_delete_answers_empty_with_htmx(signed_in, kael):
    block = Block.objects.get(tab__record=kael)
    r = signed_in.post(f"/blocos/{block.id}/apagar/", **HTMX)
    assert r.status_code == 200 and r.content == b"" and not Block.objects.filter(pk=block.pk).exists()


def test_asset_main_and_delete_answer_the_items_of_that_tab(signed_in, kael):
    tab = kael.tab_set.first()
    here, there = stored_png(kael, tab), stored_png(kael)
    r = signed_in.post(f"/arquivos/{here.id}/principal/", **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and "Principal" in html and "<html" not in html and str(there.id) not in html
    r = signed_in.post(f"/arquivos/{here.id}/excluir/", **HTMX)
    assert "Sem arquivos." in r.content.decode()


def test_asset_actions_still_redirect_without_htmx(signed_in, kael):
    tab = kael.tab_set.first()
    asset = stored_png(kael, tab)
    assert signed_in.post(f"/arquivos/{asset.id}/principal/").url == f"/r/{kael.id}/?aba={tab.id}"
    assert signed_in.post(f"/arquivos/{asset.id}/excluir/").url == f"/r/{kael.id}/?aba={tab.id}"


# O que a tela marca para o menu


def test_screens_carry_delete_urls(signed_in, campaign, kael):
    group = ListGroup.objects.create(record_type=kael.record_type, name="G")
    asset = stored_png(kael)
    tab = kael.tab_set.first()
    file_url = f'data-delete-url="/arquivos/{asset.id}/excluir/"'
    for url, expected in [
        ("/c/", f'data-delete-url="/c/{campaign.id}/apagar/"'),
        (f"/c/{campaign.id}/", f'data-delete-url="/c/{campaign.id}/t/{kael.record_type_id}/apagar/"'),
        (f"/c/{campaign.id}/t/{kael.record_type_id}/", f'data-delete-url="/r/{kael.id}/apagar/"'),
        (f"/c/{campaign.id}/t/{kael.record_type_id}/?v=galeria", f'data-delete-url="/r/{kael.id}/apagar/"'),
        (f"/c/{campaign.id}/t/{kael.record_type_id}/", f'data-delete-url="/modelo/grupo/{group.id}/remover/"'),
        (f"/r/{kael.id}/", f'data-delete-url="/abas/{tab.id}/apagar/"'),
        (f"/r/{kael.id}/?aba=galeria", file_url),
    ]:
        assert expected in signed_in.get(url).content.decode(), url


def test_only_the_open_tab_and_group_leave_the_page_when_deleted(signed_in, campaign, kael):
    group = ListGroup.objects.create(record_type=kael.record_type, name="G")
    list_url = f"/c/{campaign.id}/t/{kael.record_type_id}/"
    assert "data-delete-go" not in signed_in.get(list_url).content.decode()
    assert "data-delete-go" in signed_in.get(f"{list_url}?g={group.id}").content.decode()
    assert f'data-delete-go="/r/{kael.id}/"' in signed_in.get(f"/r/{kael.id}/").content.decode()
    assert "data-delete-go" not in signed_in.get(f"/r/{kael.id}/?aba=galeria").content.decode()
