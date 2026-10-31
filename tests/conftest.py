import pytest

from campaigns.defaults import seed_campaign
from campaigns.models import Campaign


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("ana", "ana@x.com", "S3nha-forte!")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user("bia", "bia@x.com", "S3nha-forte!")


@pytest.fixture
def make_campaign(db):
    def _make(owner, name="Vael"):
        c = Campaign.objects.create(owner=owner, name=name)
        seed_campaign(c)
        return c
    return _make


@pytest.fixture(autouse=True)
def _tmp_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
