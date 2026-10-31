import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from PIL import Image

from assets.storage import store_upload
from campaigns.models import FieldDef, ListGroup
from records.models import Block
from records.services import add_record_tab, add_subtab

from .test_indexing import make_record

# Rotas que só respondem a GET; todas as outras são testadas com POST.
GET_ROUTES = {
    "campaign-home", "type-new", "template-edit", "record-list", "record-new", "record-detail", "record-panel",
    "record-delete", "record-copy", "tracks-bulk", "campaign-export", "search", "suggest", "asset-open", "asset-file",
}


def _walk(patterns):
    for p in patterns:
        if isinstance(p, URLResolver):
            if p.namespace != "admin":  # a admin do Django é do superusuário, fora desta regra
                yield from _walk(p.url_patterns)
        elif isinstance(p, URLPattern) and p.name and p.pattern.converters:
            yield p.name, set(p.pattern.converters)


def all_parameterized_route_names():
    return {name for name, _ in _walk(get_resolver().url_patterns)}


def owner_scoped_routes():
    routes = dict(_walk(get_resolver().url_patterns))
    return [("get" if n in GET_ROUTES else "post", n, p) for n, p in sorted(routes.items())]


class World:
    """Um exemplar de cada coisa que as rotas citam por id, todos da campanha de `owner`."""

    def __init__(self, owner, campaign):
        self.campaign = campaign
        self.record = make_record(campaign, "Personagens", "Kael", body="texto")
        rtype = self.record.record_type
        FieldDef.objects.create(record_type=rtype, label="Link", kind="link", position=9)  # tracks-bulk exige um
        self.tab = self.record.tab_set.first() or add_record_tab(self.record, "Texto")
        add_subtab(self.tab, "Sub")
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, "PNG")
        self.asset = store_upload(self.record, self.tab, SimpleUploadedFile("a.png", buf.getvalue(), "image/png"))
        self.ids = {
            "campaign_id": campaign.id, "type_id": rtype.id, "record_id": self.record.id, "tab_id": self.tab.id,
            "field_id": rtype.fielddef_set.first().id, "tabdef_id": rtype.tabdef_set.first().id,
            "group_id": ListGroup.objects.create(record_type=rtype, name="G").id,
            "block_id": Block.objects.filter(tab=self.tab).first().id, "asset_id": self.asset.id,
        }

    def fill(self, params):
        return {p: self.ids[p] for p in params}


@pytest.fixture
def world(user, make_campaign):
    return World(user, make_campaign(user))


@pytest.mark.parametrize("method,name,params", owner_scoped_routes())
def test_other_master_gets_404(client, other_user, world, method, name, params):
    client.force_login(other_user)
    assert getattr(client, method)(reverse(name, kwargs=world.fill(params))).status_code == 404


@pytest.mark.parametrize("method,name,params", owner_scoped_routes())
def test_owner_does_not_get_404(client, user, world, method, name, params):
    # Sem isto, um id mal montado faria o teste acima passar por engano.
    client.force_login(user)
    assert getattr(client, method)(reverse(name, kwargs=world.fill(params))).status_code != 404


def test_every_parameterized_route_is_listed():
    assert all_parameterized_route_names() <= {n for _, n, _ in owner_scoped_routes()}
    assert {"asset-file", "asset-main", "asset-delete", "asset-open"} <= all_parameterized_route_names()
