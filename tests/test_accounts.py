import pytest


def test_signup_creates_user_and_logs_in(client, django_user_model):
    r = client.post("/cadastro", {"username": "ana", "email": "a@x.com", "password1": "S3nha-forte!", "password2": "S3nha-forte!"})
    assert r.status_code == 302
    assert django_user_model.objects.filter(username="ana").exists()
    assert "_auth_user_id" in client.session


def test_duplicate_email_rejected(client, django_user_model):
    django_user_model.objects.create_user("b", "a@x.com", "x")
    r = client.post("/cadastro", {"username": "ana", "email": "a@x.com", "password1": "S3nha-forte!", "password2": "S3nha-forte!"})
    assert r.status_code == 200 and not django_user_model.objects.filter(username="ana").exists()


def test_login_with_username(client, django_user_model):
    django_user_model.objects.create_user("ana", "a@x.com", "S3nha-forte!")
    assert client.post("/entrar", {"username": "ana", "password": "S3nha-forte!"}).status_code == 302


@pytest.mark.django_db
def test_health_does_not_touch_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert client.get("/health").status_code == 200
