import os

import pytest
from django.conf import settings

from ..test_indexing import make_record

# A API síncrona do Playwright mantém um laço de eventos na thread dos testes,
# e o Django recusaria o ORM ali sem isto.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


@pytest.fixture(scope="session")
def base_url(live_server):
    return live_server.url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, base_url):
    return {**browser_context_args, "base_url": base_url, "viewport": {"width": 390, "height": 844}}


@pytest.fixture
def logged_in(page, live_server, user, client):
    client.force_login(user)
    page.context.add_cookies([{
        "name": settings.SESSION_COOKIE_NAME,
        "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
        "url": live_server.url,
    }])


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def character(campaign):
    return make_record(campaign, "Personagens", "Kael", body="texto")


@pytest.fixture
def elf(campaign):
    return make_record(campaign, "Raças", "Elfos", body="base")
