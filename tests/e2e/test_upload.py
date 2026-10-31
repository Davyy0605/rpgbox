import io
import random
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from playwright.sync_api import expect

from assets.storage import store_upload


def gallery_url(record):
    return f"/r/{record.id}/?aba=galeria"


def make_pdf(broken_second_page=False):
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 99 0 R] /Count 2 >>" if broken_second_page
        else b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 24 Tf 20 100 Td (Ola RPGBox) Tj ET"
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


@pytest.fixture
def big_png_path(tmp_path):
    # Mais de 25 milhões de pixels, em blocos para o PNG continuar pequeno.
    rnd = random.Random(1)
    small = Image.new("RGB", (313, 313))
    small.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(313 * 313)])
    path = tmp_path / "grande.png"
    small.resize((5008, 5008), Image.NEAREST).save(path)
    return str(path)


@pytest.fixture
def record_with_pdf(character):
    return store_upload(character, None, SimpleUploadedFile("mapa.pdf", make_pdf(), "application/pdf"))


def test_large_image_is_shrunk_before_sending(page, live_server, logged_in, character, big_png_path):
    page.goto(gallery_url(character))
    with page.expect_request("**/arquivos/") as req:
        page.set_input_files("[data-dropzone] input", big_png_path)
    # O Chromium não expõe o corpo quando há Blob no FormData; o tamanho vem do cabeçalho.
    assert int(req.value.all_headers()["content-length"]) < 1_500_000
    expect(page.locator("[data-gallery] img")).to_have_count(1)
    asset = character.asset_set.get()
    assert max(asset.width, asset.height) <= 1600


def test_server_error_shown_in_the_zone(page, live_server, logged_in, character):
    page.goto(gallery_url(character))
    page.set_input_files("[data-dropzone] input", files=[
        {"name": "x.pdf", "mimeType": "application/pdf", "buffer": b"<html>"}])
    expect(page.locator("[data-dropzone] [role=alert]")).to_contain_text("PDF")


def test_pdf_renders_inside_site(page, live_server, logged_in, record_with_pdf):
    page.goto(f"/arquivos/{record_with_pdf.id}/")
    expect(page.locator("[data-pdf-url] canvas").first).to_be_visible()


def test_pdf_follows_redirect_to_other_origin(page, live_server, logged_in, record_with_pdf):
    # Imita o R2: outra origem, com CORS aberto, para onde o arquivo do site redireciona.
    pdf = make_pdf()

    class Signed(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(pdf)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Signed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = f"http://127.0.0.1:{server.server_port}/mapa.pdf"
    page.route("**/arquivos/*/arquivo/*", lambda route: route.fulfill(status=302, headers={"Location": target}))
    try:
        page.goto(f"/arquivos/{record_with_pdf.id}/")
        expect(page.locator("[data-pdf-url] canvas").first).to_be_visible()
    finally:
        server.shutdown()


def test_pdf_worker_served_from_site(live_server):
    with urlopen(live_server.url + "/static/js/pdf.worker.js") as r:
        assert r.status == 200 and len(r.read()) > 100_000


def test_expired_session_is_reported(page, live_server, logged_in, character, big_png_path):
    page.goto(gallery_url(character))
    page.context.clear_cookies(name=settings.SESSION_COOKIE_NAME)  # a sessão vence; o cookie CSRF fica
    page.set_input_files("[data-dropzone] input", big_png_path)
    alert = page.locator("[data-dropzone] [role=alert]")
    expect(alert).to_contain_text("Sessão expirada")
    expect(alert.get_by_role("link")).to_have_attribute("href", re.compile(r"^/entrar\?next="))
    assert character.asset_set.count() == 0


PASTE = """async (name) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 20;
    canvas.getContext("2d").fillRect(0, 0, 20, 20);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
    const data = new DataTransfer();
    data.items.add(new File([blob], name, {type: "image/png"}));
    document.body.dispatchEvent(new ClipboardEvent("paste", {clipboardData: data, bubbles: true, cancelable: true}));
}"""


def test_pastes_during_an_upload_are_queued(page, live_server, logged_in, character):
    page.goto(gallery_url(character))
    page.evaluate(PASTE, "um.png")
    page.evaluate(PASTE, "dois.png")
    expect(page.locator("[data-gallery] img")).to_have_count(2)
    assert character.asset_set.count() == 2


def test_partial_failure_shows_uploaded_and_names_failures(page, live_server, logged_in, character):
    page.goto(gallery_url(character))
    ok = io.BytesIO()
    Image.new("RGB", (30, 30), "red").save(ok, "PNG")
    page.set_input_files("[data-dropzone] input", files=[
        {"name": "bom.png", "mimeType": "image/png", "buffer": ok.getvalue()},
        {"name": "ruim.pdf", "mimeType": "application/pdf", "buffer": b"<html>"}])
    expect(page.locator("[data-gallery] img")).to_have_count(1)
    expect(page.locator("[data-dropzone] [role=alert]")).to_contain_text("ruim.pdf")


def test_pdf_page_error_keeps_link_and_recovers(page, live_server, logged_in, character):
    asset = store_upload(character, None, SimpleUploadedFile(
        "dois.pdf", make_pdf(broken_second_page=True), "application/pdf"))
    page.goto(f"/arquivos/{asset.id}/")
    expect(page.locator("[data-pdf-url] canvas").first).to_be_visible()
    page.get_by_role("button", name="Próxima").click()
    alert = page.locator("[data-pdf-url] [role=alert]")
    expect(alert).to_be_visible()
    expect(alert.get_by_role("link", name="Abrir PDF")).to_be_visible()
    expect(page.locator("[data-pdf-url]")).to_contain_text("Página 2 de 2")
    page.get_by_role("button", name="Anterior").click()
    expect(alert).to_be_hidden()
    expect(page.locator("[data-pdf-url]")).to_contain_text("Página 1 de 2")
