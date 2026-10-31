import io

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from assets.images import InvalidFile
from assets.models import Asset
from assets.storage import asset_url, kind_of_open, storage_used, store_upload
from records.services import create_record


def upload(name, data, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def _img(fmt, size, **kw):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, fmt, **kw)
    return buf.getvalue()


@pytest.fixture
def campaign(user, make_campaign):
    return make_campaign(user)


@pytest.fixture
def record(campaign):
    return create_record(campaign.recordtype_set.get(name="Personagens"), "Kael")


@pytest.fixture
def big_jpeg_5000px():
    return upload("IMG_1.jpg", _img("JPEG", (5000, 3000)), "image/jpeg")


@pytest.fixture
def small_png():
    return upload("a.png", _img("PNG", (50, 40)), "image/png")


def test_iphone_jpeg_becomes_small_webp(record, big_jpeg_5000px):
    a = store_upload(record, None, big_jpeg_5000px)
    img = Image.open(default_storage.open(a.key))
    assert img.format == "WEBP" and max(img.size) == 1600 and a.kind == "image"
    assert max(Image.open(default_storage.open(a.thumb_key)).size) == 400


def test_exif_rotation_applied(record):
    im = Image.new("RGB", (200, 100), (1, 2, 3))
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    a = store_upload(record, None, upload("r.jpg", buf.getvalue()))
    assert (a.width, a.height) == (100, 200)


def test_animated_gif_becomes_static(record):
    frames = [Image.new("RGB", (30, 30), c) for c in ((255, 0, 0), (0, 255, 0))]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    a = store_upload(record, None, upload("a.gif", buf.getvalue()))
    img = Image.open(default_storage.open(a.key))
    assert getattr(img, "n_frames", 1) == 1


def test_svg_disguised_as_png_rejected(record):
    with pytest.raises(InvalidFile):
        store_upload(record, None, upload("x.png", b"<svg onload=alert(1)>"))


def test_html_rejected(record):
    with pytest.raises(InvalidFile):
        store_upload(record, None, upload("a.html", b"<html>"))


def test_corrupt_image_rejected(record):
    with pytest.raises(InvalidFile):
        store_upload(record, None, upload("x.jpg", b"\xff\xd8quebrado"))


def test_fake_pdf_and_fake_docx_rejected(record):
    with pytest.raises(InvalidFile):
        store_upload(record, None, upload("a.pdf", b"<html>"))
    with pytest.raises(InvalidFile):
        store_upload(record, None, upload("a.docx", b"<html>"))


def test_file_over_25mb_shows_message(client, record, user):
    client.force_login(user)
    r = client.post(f"/r/{record.id}/arquivos/", {"file": upload("a.pdf", b"%PDF-" + b"0" * (25 * 1024 * 1024))})
    assert r.status_code == 400 and "25 MB" in r.content.decode()


def test_image_over_25mb_shows_message(client, record, user):
    client.force_login(user)
    r = client.post(f"/r/{record.id}/arquivos/", {"file": upload("a.png", b"\x89PNG" + b"0" * (25 * 1024 * 1024))})
    assert r.status_code == 400 and "25 MB" in r.content.decode()


def test_pdf_opens_inline_docx_downloads(record):
    pdf = store_upload(record, None, upload("a.pdf", b"%PDF-1.4"))
    docx = store_upload(record, None, upload("a.docx", b"PK\x03\x04"))
    assert kind_of_open(pdf) == "viewer" and kind_of_open(docx) == "download"


def test_first_gallery_image_becomes_main(record, small_png):
    a = store_upload(record, None, small_png)
    record.refresh_from_db()
    assert record.main_image == a


def test_deleting_asset_removes_storage_and_main(record, small_png):
    a = store_upload(record, None, small_png)
    key, thumb = a.key, a.thumb_key
    a.delete()
    record.refresh_from_db()
    assert record.main_image is None and not default_storage.exists(key) and not default_storage.exists(thumb)


def test_filename_is_not_used_as_storage_key(record):
    a = store_upload(record, None, upload("../../x.pdf", b"%PDF-1.4"))
    assert ".." not in a.key and a.filename == "x.pdf"


def test_storage_used_sums_owner_files(record, user, other_user, small_png):
    a = store_upload(record, None, small_png)
    assert storage_used(user) == a.size > 0
    assert storage_used(other_user) == 0


def test_asset_url_filesystem(record, small_png):
    a = store_upload(record, None, small_png)
    assert asset_url(a, "thumb").endswith(a.thumb_key)
    assert asset_url(a).endswith(a.key)


# views

def test_upload_view_stores_and_redirects(client, record, user, small_png):
    client.force_login(user)
    r = client.post(f"/r/{record.id}/arquivos/", {"file": small_png})
    assert r.status_code == 302
    assert Asset.objects.filter(record=record).count() == 1


def test_upload_invalid_shows_message(client, record, user):
    client.force_login(user)
    r = client.post(f"/r/{record.id}/arquivos/", {"file": upload("a.html", b"<html>")})
    assert r.status_code == 400 and "Tipo de arquivo" in r.content.decode()


def test_upload_to_foreign_record_404(client, record, other_user, small_png):
    client.force_login(other_user)
    assert client.post(f"/r/{record.id}/arquivos/", {"file": small_png}).status_code == 404


def test_upload_with_tab_of_other_record_404(client, record, user, campaign, small_png):
    other = create_record(campaign.recordtype_set.get(name="Personagens"), "Outro")
    tab = other.tab_set.first()
    client.force_login(user)
    assert client.post(f"/r/{record.id}/arquivos/", {"file": small_png, "tab": tab.id}).status_code == 404


def test_open_pdf_viewer_and_docx_attachment(client, record, user):
    pdf = store_upload(record, None, upload("a.pdf", b"%PDF-1.4"))
    docx = store_upload(record, None, upload("a.docx", b"PK\x03\x04"))
    client.force_login(user)
    r = client.get(f"/arquivos/{pdf.id}/")
    assert r.status_code == 200 and "data-pdf-url" in r.content.decode()
    r = client.get(f"/arquivos/{docx.id}/")
    assert "attachment" in r["Content-Disposition"]


def test_open_other_users_asset_404(client, record, other_user, small_png):
    a = store_upload(record, None, small_png)
    client.force_login(other_user)
    assert client.get(f"/arquivos/{a.id}/").status_code == 404


def test_set_main_and_delete_views(client, record, user, small_png):
    a = store_upload(record, None, small_png)
    b = store_upload(record, None, upload("b.png", _img("PNG", (10, 10))))
    client.force_login(user)
    client.post(f"/arquivos/{b.id}/principal/")
    record.refresh_from_db()
    assert record.main_image == b
    client.post(f"/arquivos/{b.id}/excluir/")
    record.refresh_from_db()
    assert record.main_image is None and not Asset.objects.filter(pk=b.id).exists()
    assert Asset.objects.filter(pk=a.id).exists()


def test_gallery_tab_lists_images(client, record, user, small_png):
    store_upload(record, None, small_png)
    client.force_login(user)
    r = client.get(f"/r/{record.id}/?aba=galeria")
    assert "<img" in r.content.decode()


def test_campaign_list_shows_storage(client, record, user, small_png):
    store_upload(record, None, small_png)
    client.force_login(user)
    assert "Espaço usado" in client.get("/c/").content.decode()
