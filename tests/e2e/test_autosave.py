import json
import re

import pytest
from django.db.utils import OperationalError
from playwright.sync_api import expect

from records.models import Block
from records.save import save_block, save_field

from ..helpers import doc, doc_with_link
from ..test_indexing import make_record, set_body
from .test_editor import FIELD, TEXT, block_of, saved, texts, url_of

BLOCK_SAVE = re.compile(r"/blocos/\d+/$")
FIELD_SAVE = re.compile(r"/campos/$")
BLOCK_CREATE = re.compile(r"/abas/\d+/blocos/$")
MINE = "Neste aparelho"
THEIRS = "Em outro aparelho"
CONFLICT = "Alterado em outro aparelho"
RETRIED = 20000  # a primeira repetição vem em 3 s, somados ao envio perdido; a máquina pode estar ocupada


@pytest.fixture
def text_block(character):
    return Block.objects.get(tab__record=character, kind="text")


@pytest.fixture
def text_block_url(character):
    return url_of(character)


def block_key(block):
    return f"rascunho:/blocos/{block.id}/"


def field_key(record, label):
    return record.record_type.fielddef_set.get(label=label).key


def draft(page, key):
    return page.evaluate("k => JSON.parse(localStorage.getItem(k))", key)


def seed_draft(page, key, value, version):
    page.goto("/health")
    page.evaluate("([k, d]) => localStorage.setItem(k, JSON.stringify(d))",
                  [key, {"value": value, "version": version}])


def use(page, side):
    page.get_by_role("group", name=side).get_by_role("button", name="Usar esta").click()


def type_at_end(page, text, selector=TEXT):
    page.locator(selector).click()
    page.keyboard.press("Control+End")
    page.keyboard.type(text)


def stop_the_clock(page, url):
    """Só `clock.run_for` passa o tempo da página depois disto."""
    page.clock.install(time=0)
    page.goto(url)
    expect(page.locator(TEXT)).to_be_visible()
    page.clock.pause_at(3600000)


def wait_no_drafts(page):
    page.wait_for_function("!Object.keys(localStorage).some(k => k.startsWith('rascunho:'))")


def read_db(page, read):
    """Lê o banco depois de um envio cuja resposta a página não viu.

    O pedido abandonado pelo recarregamento ainda pode estar gravando, e no SQLite em
    memória, que o teste divide com o servidor, ler nessa hora dá "table is locked".
    """
    for _ in range(20):
        try:
            return read()
        except OperationalError:
            page.wait_for_timeout(100)
    return read()


def lose_answers(page, pattern, times=1):
    """O servidor processa o pedido, mas a resposta se perde no caminho."""
    lost = []

    def handler(route):
        if len(lost) < times:
            lost.append(route.request.url)
            route.fetch()
            route.abort()
        else:
            route.continue_()

    page.route(pattern, handler)
    return lost


# Rascunho e reenvio

def test_text_survives_offline_and_reload(page, context, live_server, logged_in, text_block_url):
    page.goto(text_block_url); context.set_offline(True)
    page.locator(TEXT).click(); page.keyboard.type("ideia nova")
    expect(page.get_by_text("Sem conexão, tentando de novo")).to_be_visible(timeout=RETRIED)
    context.set_offline(False); page.reload()
    expect(page.locator(TEXT)).to_contain_text("ideia nova")


def test_status_shows_saving_then_saved(page, live_server, logged_in, character, text_block):
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(character))
    type_at_end(page, " novo")
    expect(page.get_by_text("Salvando")).to_be_visible()
    page.wait_for_timeout(1000)
    held[0].continue_()
    expect(page.get_by_text("Salvo")).to_be_visible()


def test_draft_lives_until_the_server_answers_200(page, live_server, logged_in, character, text_block):
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(character))
    type_at_end(page, " novo")
    page.wait_for_timeout(1000)
    assert held
    found = draft(page, block_key(text_block))
    assert found["version"] == 1 and found["value"]["content"][0]["content"][0]["text"] == "texto novo"
    held[0].continue_()
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert draft(page, block_key(text_block)) is None


def test_typing_during_a_send_keeps_the_newer_draft(page, live_server, logged_in, character, text_block):
    held = []

    def hold_first(route):
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route(BLOCK_SAVE, hold_first)
    page.goto(url_of(character))
    type_at_end(page, " um")
    page.wait_for_timeout(1000)
    assert len(held) == 1
    page.keyboard.type(" dois")
    with page.expect_response(lambda r: BLOCK_SAVE.search(r.url) and "dois" in r.request.post_data) as second:
        held[0].continue_()
        # Antes de o segundo envio responder, o rascunho já tem a versão nova e o texto novo.
        page.wait_for_function("""k => {
            const draft = JSON.parse(localStorage.getItem(k));
            return draft?.version === 2 && draft.value.content[0].content[0].text === "texto um dois";
        }""", arg=block_key(text_block))
    assert second.value.status == 200
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert draft(page, block_key(text_block)) is None
    assert texts(block_of(character)) == ["texto um dois"]


def test_back_online_saves_without_reloading(page, context, live_server, logged_in, character, text_block):
    page.goto(url_of(character))
    context.set_offline(True)
    type_at_end(page, " volta")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    with page.expect_response(BLOCK_SAVE) as info:
        context.set_offline(False)
    assert info.value.status == 200
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert texts(block_of(character)) == ["texto volta"]


def test_retries_at_3_10_30_and_then_every_30_seconds(page, live_server, logged_in, character, text_block):
    attempts = []
    page.route(BLOCK_SAVE, lambda route: (attempts.append(1), route.abort()))
    stop_the_clock(page, url_of(character))
    type_at_end(page, "x")

    def advance(ms, expected):
        page.clock.run_for(ms)
        page.wait_for_timeout(150)
        assert len(attempts) == expected

    advance(700, 0)
    advance(100, 1)
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    for wait in (3000, 10000, 30000, 30000, 30000):
        expected = len(attempts)
        advance(wait - 100, expected)
        advance(100, expected + 1)


def test_a_hung_send_gives_up_after_90_seconds_and_retries(page, live_server, logged_in, character, text_block):
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    stop_the_clock(page, url_of(character))
    type_at_end(page, "x")
    page.clock.run_for(800)
    page.wait_for_timeout(150)
    assert len(held) == 1
    page.clock.run_for(89000)
    page.wait_for_timeout(150)
    expect(page.get_by_text("Salvando")).to_be_visible()
    page.clock.run_for(1100)
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    page.wait_for_timeout(150)
    page.clock.run_for(3000)
    page.wait_for_timeout(150)
    assert len(held) == 2


def test_server_waking_with_503_is_retried(page, live_server, logged_in, character, text_block):
    count = []

    def waking(route):
        count.append(1)
        if len(count) == 1:
            route.fulfill(status=503, body="acordando")
        else:
            route.continue_()

    page.route(BLOCK_SAVE, waking)
    page.goto(url_of(character))
    type_at_end(page, " acordou")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    assert draft(page, block_key(text_block)) is not None
    expect(page.get_by_text("Salvo")).to_be_visible(timeout=RETRIED)
    assert draft(page, block_key(text_block)) is None
    assert texts(block_of(character)) == ["texto acordou"]


def test_200_without_a_version_does_not_drop_the_draft(page, live_server, logged_in, character, text_block):
    page.route(BLOCK_SAVE, lambda route: route.fulfill(status=200, content_type="text/html", body="<p>acordando</p>"))
    page.goto(url_of(character))
    type_at_end(page, " x")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    assert draft(page, block_key(text_block)) is not None


def test_lost_answer_is_not_a_conflict(page, live_server, logged_in, character, text_block):
    lose_answers(page, BLOCK_SAVE)
    page.goto(url_of(character))
    type_at_end(page, " uma vez")
    expect(page.get_by_text("Salvo")).to_be_visible(timeout=RETRIED)
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    assert draft(page, block_key(text_block)) is None
    assert block_of(character).version == 2
    saved(page, lambda: page.keyboard.type("!"), "uma vez!")


def test_lost_answer_with_more_typing_is_not_a_conflict(page, live_server, logged_in, character, text_block):
    lost = lose_answers(page, BLOCK_SAVE)
    page.goto(url_of(character))
    type_at_end(page, " um")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    assert lost
    page.keyboard.type(" dois")
    expect(page.get_by_text("Salvo")).to_be_visible(timeout=RETRIED)
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    assert texts(block_of(character)) == ["texto um dois"]


def test_expired_session_warns_and_keeps_the_draft(page, context, live_server, logged_in, character, text_block):
    page.goto(url_of(character))
    context.clear_cookies(name="sessionid")
    type_at_end(page, " x")
    expect(page.get_by_text("Sessão expirada")).to_be_visible()
    assert draft(page, block_key(text_block)) is not None


def test_rejected_text_shows_why_and_keeps_the_draft(page, live_server, logged_in, character, text_block):
    page.route(BLOCK_SAVE, lambda route: route.fulfill(
        status=400, content_type="application/json", body='{"error": "Documento inválido."}'))
    page.goto(url_of(character))
    type_at_end(page, " x")
    expect(page.get_by_text("Não foi possível salvar. Documento inválido.")).to_be_visible()
    assert draft(page, block_key(text_block)) is not None


def test_deleted_block_is_visible_and_keeps_the_text(page, live_server, logged_in, character, text_block):
    key = block_key(text_block)
    page.goto(url_of(character))
    text_block.delete()
    type_at_end(page, " x")
    expect(page.get_by_text("não existe mais")).to_be_visible()
    expect(page.locator(TEXT)).to_contain_text("texto x")
    assert draft(page, key) is not None


def test_leaving_the_page_sends_at_once(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character))
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    type_at_end(page, " x")
    page.evaluate("""() => {
        Object.defineProperty(document, "visibilityState", {value: "hidden", configurable: true});
        document.dispatchEvent(new Event("visibilitychange"));
    }""")
    page.wait_for_timeout(150)
    assert len(held) == 1


def test_leaving_the_page_with_a_big_text_still_sends(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character))
    page.locator(TEXT).click()
    page.keyboard.press("Control+End")
    page.keyboard.insert_text("a" * 70000)
    with page.expect_response(BLOCK_SAVE) as info:
        page.evaluate("""() => {
            Object.defineProperty(document, "visibilityState", {value: "hidden", configurable: true});
            document.dispatchEvent(new Event("visibilitychange"));
        }""")
    assert info.value.status == 200
    expect(page.get_by_text("Sem conexão")).to_have_count(0)


def watch_keepalive(page):
    """Anota como foi o último envio. A navegação é de verdade: nada aqui finge a visibilidade."""
    page.add_init_script("""
        const realFetch = window.fetch;
        window.fetch = (url, options) => {
            if (options?.method === "POST") sessionStorage.setItem("keepalive", String(options.keepalive));
            return realFetch(url, options);
        };
    """)


def sent_with_keepalive(page):
    return page.evaluate("sessionStorage.getItem('keepalive')") == "true"


def server_has(page, read, wanted):
    """Espera o servidor receber o texto; a página que o enviou já foi embora."""
    for _ in range(50):
        if read_db(page, read) == wanted:
            return True
        page.wait_for_timeout(100)
    return False


def test_following_a_link_right_after_typing_reaches_the_server(page, live_server, logged_in, character, text_block):
    watch_keepalive(page)
    stop_the_clock(page, url_of(character))  # o relógio parado segura o envio de 800 ms: só resta o da saída
    type_at_end(page, " antes de sair")
    page.locator("a.brand").click()
    page.wait_for_url("**/")
    assert server_has(page, lambda: texts(block_of(character)), ["texto antes de sair"])
    assert sent_with_keepalive(page)


def test_reloading_right_after_typing_reaches_the_server(page, live_server, logged_in, character, text_block):
    # Sem rascunho na volta: quem salva é o envio feito ao sair, e não o reenvio ao abrir.
    watch_keepalive(page)
    stop_the_clock(page, url_of(character))
    page.add_init_script("""Object.keys(localStorage).forEach(k => localStorage.removeItem(k));""")
    type_at_end(page, " antes de recarregar")
    page.reload()
    assert server_has(page, lambda: texts(block_of(character)), ["texto antes de recarregar"])
    assert sent_with_keepalive(page)


def test_leaving_right_after_typing_in_a_field_reaches_the_server(page, live_server, logged_in, character):
    key = field_key(character, "Ocupação")
    watch_keepalive(page)
    stop_the_clock(page, url_of(character))
    page.get_by_label("Ocupação").fill("Bardo")
    page.locator("a.brand").click()
    page.wait_for_url("**/")

    def read():
        character.refresh_from_db()
        return character.fields.get(key)

    assert server_has(page, read, "Bardo")
    assert sent_with_keepalive(page)


def test_leaving_during_a_send_sends_again_with_keepalive(page, live_server, logged_in, character, text_block):
    held = []

    def hold_first(route):
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route(BLOCK_SAVE, hold_first)
    watch_keepalive(page)
    page.goto(url_of(character))
    type_at_end(page, " em andamento")
    page.wait_for_timeout(1200)
    assert len(held) == 1
    page.locator("a.brand").click()
    page.wait_for_url("**/")
    assert server_has(page, lambda: texts(block_of(character)), ["texto em andamento"])
    assert sent_with_keepalive(page)


# Duas abas

def test_second_tab_does_not_eat_the_draft_of_the_first(page, context, live_server, logged_in, character, text_block):
    # A primeira aba fica sem rede e é fechada; a segunda salva por cima do mesmo texto.
    second = context.new_page()
    second.goto(url_of(character))
    page.goto(url_of(character))
    context.set_offline(True)
    type_at_end(page, " aaaa")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    page.close()
    context.set_offline(False)

    saved(second, lambda: type_at_end(second, " bbbb"), "bbbb")
    assert texts(block_of(character)) == ["texto bbbb"]
    expect(second.get_by_text(CONFLICT)).to_have_count(0)

    second.reload()
    expect(second.get_by_text(CONFLICT)).to_be_visible()
    expect(second.get_by_role("group", name=MINE)).to_contain_text("aaaa")
    expect(second.get_by_role("group", name=THEIRS)).to_contain_text("bbbb")


def test_answer_in_one_tab_does_not_delete_the_newer_draft_of_the_other(page, context, live_server, logged_in,
                                                                        character, text_block):
    held = []

    def hold_a(route):
        if "texto b" in (route.request.post_data or ""):
            route.abort()
        elif held:
            route.continue_()
        else:
            held.append(route)

    context.route(BLOCK_SAVE, hold_a)
    second = context.new_page()
    second.goto(url_of(character))
    page.goto(url_of(character))
    type_at_end(page, " aaaa")
    page.wait_for_timeout(1000)
    assert held
    type_at_end(second, " bbbb")
    expect(second.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    held[0].continue_()
    expect(page.get_by_text("Salvo")).to_be_visible()

    stored = second.evaluate("""() => Object.keys(localStorage).filter(k => k.startsWith("rascunho:"))
        .map(k => localStorage.getItem(k))""")
    assert len(stored) == 1 and "bbbb" in stored[0]
    context.unroute(BLOCK_SAVE)
    second.reload()
    expect(second.get_by_text(CONFLICT)).to_be_visible()
    expect(second.get_by_role("group", name=MINE)).to_contain_text("bbbb")


def test_tab_draft_is_not_dropped_unread_when_a_block_draft_comes_first(page, live_server, logged_in, character,
                                                                        text_block):
    tab_key = f"rascunho:/abas/{text_block.tab_id}/blocos/"
    seed_draft(page, block_key(text_block), doc("do bloco"), 1)
    page.evaluate("([k, d]) => localStorage.setItem(k, JSON.stringify(d))",
                  [tab_key, {"value": doc("da aba"), "version": None}])
    with page.expect_response(BLOCK_SAVE):
        page.goto(url_of(character))
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert draft(page, tab_key) is not None
    page.reload()
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("da aba")
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("do bloco")


def test_two_tabs_on_an_empty_tab_keep_both_drafts(page, context, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    context.route(BLOCK_CREATE, lambda route: route.abort())
    second = context.new_page()
    second.goto(url_of(empty))
    page.goto(url_of(empty))
    page.locator(TEXT).click(); page.keyboard.type("de A")
    second.locator(TEXT).click(); second.keyboard.type("de B")
    expect(second.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    stored = second.evaluate("""() => Object.keys(localStorage).filter(k => k.startsWith("rascunho:"))
        .map(k => localStorage.getItem(k)).join()""")
    assert "de A" in stored and "de B" in stored


# Aparelho sem espaço para o rascunho

AT_RISK = "não conseguiu guardar"


def fill_storage(page, prefix="rascunho:"):
    page.add_init_script("""(prefix => {
        const real = Storage.prototype.setItem;
        Storage.prototype.setItem = function (key, value) {
            if (location.pathname !== "/health" && key.startsWith(prefix)) {
                throw new DOMException("cheio", "QuotaExceededError");
            }
            real.call(this, key, value);
        };
    })(%s);""" % json.dumps(prefix))


def status_with(page, text):
    return page.locator(".save-status", has_text=text)


def test_full_storage_warns_while_offline(page, context, live_server, logged_in, character, text_block):
    fill_storage(page)
    page.goto(url_of(character))
    context.set_offline(True)
    type_at_end(page, " x")
    expect(status_with(page, "Sem conexão")).to_contain_text(AT_RISK, timeout=RETRIED)
    context.set_offline(False)


def test_full_storage_never_promises_the_text_is_on_the_device(page, live_server, logged_in, character, text_block):
    fill_storage(page)
    page.route(BLOCK_SAVE, lambda route: route.fulfill(
        status=400, content_type="application/json", body='{"error": "Documento inválido."}'))
    page.goto(url_of(character))
    type_at_end(page, " x")
    message = status_with(page, "Não foi possível salvar")
    expect(message).to_contain_text(AT_RISK)
    expect(message).not_to_contain_text("segue neste aparelho")


def test_full_storage_warning_goes_away_once_saved(page, live_server, logged_in, character, text_block):
    fill_storage(page)
    page.goto(url_of(character))
    saved(page, lambda: type_at_end(page, " x"), "texto x")
    expect(page.get_by_text("Salvo")).to_be_visible()
    expect(status_with(page, AT_RISK)).to_have_count(0)


def test_session_warning_does_not_promise_the_device_when_storage_is_full(page, context, live_server, logged_in,
                                                                          character, text_block):
    fill_storage(page)
    page.goto(url_of(character))
    context.clear_cookies(name="sessionid")
    type_at_end(page, " x")
    message = status_with(page, "Sessão expirada")
    expect(message).to_contain_text(AT_RISK)
    expect(message).not_to_contain_text("segue neste aparelho")


def test_tab_draft_stays_when_the_block_draft_cannot_be_written(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab_key = f"rascunho:/abas/{empty.tab_set.order_by('position', 'id').first().id}/blocos/"
    fill_storage(page, "rascunho:/blocos/")
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(empty))
    page.locator(TEXT).click(); page.keyboard.type("oi")
    page.wait_for_timeout(1200)
    assert held
    assert draft(page, tab_key)["value"] == doc("oi")
    expect(status_with(page, "Salvando")).to_contain_text(AT_RISK)


def test_recovered_tab_draft_stays_until_the_new_one_is_written(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab = empty.tab_set.order_by("position", "id").first()
    Block.objects.create(tab=tab, kind="text", content={"type": "doc", "content": []})
    fill_storage(page, "rascunho:/blocos/")
    seed_draft(page, f"rascunho:/abas/{tab.id}/blocos/", doc("quase perdi"), None)
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(empty))
    expect(page.locator(TEXT)).to_have_text("quase perdi")
    page.wait_for_timeout(300)
    assert held
    assert draft(page, f"rascunho:/abas/{tab.id}/blocos/")["value"] == doc("quase perdi")


def test_conflict_choice_keeps_the_old_draft_until_the_new_one_is_written(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab = empty.tab_set.order_by("position", "id").first()
    Block.objects.create(tab=tab, kind="text", content=doc("do pc"), version=2)
    fill_storage(page, "rascunho:/blocos/")
    seed_draft(page, f"rascunho:/abas/{tab.id}/blocos/", doc("do celular"), None)
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(empty))
    use(page, MINE)
    page.wait_for_timeout(300)
    assert held
    assert draft(page, f"rascunho:/abas/{tab.id}/blocos/")["value"] == doc("do celular")


def test_retrying_one_text_does_not_forget_the_older_send_that_arrived(page, live_server, logged_in, character,
                                                                       text_block):
    seen = []

    def handler(route):
        seen.append(1)
        if len(seen) == 1:
            route.fetch()
            route.abort()
        elif len(seen) <= 8:
            route.abort()
        else:
            route.continue_()

    page.route(BLOCK_SAVE, handler)
    stop_the_clock(page, url_of(character))
    type_at_end(page, " um")
    page.clock.run_for(800)
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    page.keyboard.type(" dois")
    page.clock.run_for(800)
    page.wait_for_timeout(200)
    for _ in range(8):
        page.clock.run_for(30000)
        page.wait_for_timeout(200)
    expect(page.get_by_text("Salvo")).to_be_visible(timeout=RETRIED)
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    assert texts(block_of(character)) == ["texto um dois"]


# Conflito

def test_conflict_shows_both_versions(page, live_server, logged_in, text_block, text_block_url):
    page.goto(text_block_url); save_block(text_block, doc("do pc"), 1)
    page.locator(TEXT).click(); page.keyboard.type("celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_text("do pc")).to_be_visible()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("celular")
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("do pc")
    expect(page.get_by_role("button", name="Usar esta")).to_have_count(2)


def test_conflict_keep_mine_saves_with_the_new_version(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    response = saved(page, lambda: use(page, MINE), "celular")
    assert json.loads(response.request.post_data)["version"] == 2
    assert texts(block_of(character)) == ["texto celular"]
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    expect(page.get_by_text("Salvo")).to_be_visible()
    page.locator(TEXT).click()
    saved(page, lambda: page.keyboard.type("!"), "!")


def test_conflict_keep_theirs_replaces_the_editor(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    response = saved(page, lambda: use(page, THEIRS), "do pc")
    assert json.loads(response.request.post_data)["version"] == 2
    expect(page.locator(TEXT)).to_have_text("do pc")
    assert texts(block_of(character)) == ["do pc"]
    assert draft(page, block_key(text_block)) is None


def test_typing_is_locked_during_a_conflict_and_nothing_is_sent(page, live_server, logged_in, character, text_block):
    posts = []
    page.on("request", lambda r: posts.append(r.url) if BLOCK_SAVE.search(r.url) else None)
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    sent = len(posts)
    page.wait_for_timeout(1200)
    assert len(posts) == sent
    expect(page.locator(TEXT)).to_have_attribute("contenteditable", "false")


def test_reloading_during_a_conflict_does_not_overwrite(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    page.reload()
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("celular")
    page.wait_for_timeout(1200)
    assert texts(block_of(character)) == ["do pc"]


def test_conflict_of_the_last_keystrokes_shows_them(page, live_server, logged_in, character, text_block):
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " um")
    page.wait_for_timeout(1000)
    page.keyboard.type(" dois")
    held[0].continue_()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("texto um dois")


def test_second_conflict_after_choosing_opens_again(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character)); save_block(text_block, doc("do pc"), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    save_block(text_block, doc("do tablet"), 2)
    use(page, MINE)
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("do tablet")
    assert texts(block_of(character)) == ["do tablet"]


# Rascunhos ao abrir

def test_draft_at_the_current_version_is_applied_and_resent(page, live_server, logged_in, character, text_block):
    seed_draft(page, block_key(text_block), doc("escrito antes"), 1)
    with page.expect_response(BLOCK_SAVE) as info:
        page.goto(url_of(character))
    assert info.value.status == 200
    expect(page.locator(TEXT)).to_have_text("escrito antes")
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert texts(block_of(character)) == ["escrito antes"]
    assert draft(page, block_key(text_block)) is None


def test_draft_older_than_the_server_goes_to_the_conflict_screen(page, live_server, logged_in, character, text_block):
    save_block(text_block, doc("do pc"), 1)
    seed_draft(page, block_key(text_block), doc("velho"), 1)
    page.goto(url_of(character))
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("velho")
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("do pc")
    page.wait_for_timeout(1200)
    assert texts(block_of(character)) == ["do pc"]
    response = saved(page, lambda: use(page, MINE), "velho")
    assert json.loads(response.request.post_data)["version"] == 2


def test_draft_equal_to_the_server_is_dropped_quietly(page, live_server, logged_in, character, text_block):
    save_block(text_block, doc("igual"), 1)
    seed_draft(page, block_key(text_block), doc("igual"), 1)
    page.goto(url_of(character))
    expect(page.locator(TEXT)).to_have_text("igual")
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    page.wait_for_function("k => localStorage.getItem(k) === null", arg=block_key(text_block))
    assert block_of(character).version == 2


def test_draft_equal_except_for_the_attrs_the_server_drops_is_equal(page, live_server, logged_in, character, text_block):
    assert save_block(text_block, doc_with_link("site", "https://exemplo.com"), 1).ok
    from_editor = doc_with_link("site", "https://exemplo.com")
    from_editor["content"][0]["content"][0]["marks"][0]["attrs"].update(
        target="_blank", rel="noopener noreferrer nofollow", **{"class": None})
    seed_draft(page, block_key(text_block), from_editor, 1)
    page.goto(url_of(character))
    expect(page.get_by_text(CONFLICT)).to_have_count(0)
    wait_no_drafts(page)


def test_refused_older_text_does_not_stop_the_newer_one(page, live_server, logged_in, character, text_block):
    held = []

    def refuse_first(route):
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route(BLOCK_SAVE, refuse_first)
    page.goto(url_of(character))
    type_at_end(page, " um")
    page.wait_for_timeout(1000)
    page.keyboard.type(" dois")
    page.wait_for_timeout(1000)
    held[0].fulfill(status=400, content_type="application/json", body='{"error": "Documento inválido."}')
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert texts(block_of(character)) == ["texto um dois"]


def test_one_block_draft_never_opens_in_another(page, live_server, logged_in, character, text_block):
    other = Block.objects.create(tab=text_block.tab, kind="text", position=9, content=doc("outro"))
    seed_draft(page, block_key(text_block), doc("só do primeiro"), 1)
    page.goto(url_of(character))
    blocks = page.locator(TEXT)
    expect(blocks.nth(0)).to_have_text("só do primeiro")
    expect(blocks.nth(1)).to_have_text("outro")
    expect(page.get_by_text("Salvo")).to_be_visible()
    other.refresh_from_db()
    assert other.version == 1


def test_a_draft_that_does_not_fit_the_editor_is_ignored(page, live_server, logged_in, character, text_block):
    seed_draft(page, block_key(text_block), {"type": "doc", "content": [{"type": "iframe"}]}, 1)
    page.goto(url_of(character))
    expect(page.locator(TEXT)).to_have_text("texto")
    page.wait_for_timeout(1200)
    assert block_of(character).version == 1


def test_corrupt_draft_does_not_break_the_page(page, live_server, logged_in, character, text_block):
    page.goto("/health")
    page.evaluate("k => localStorage.setItem(k, '{quebrado')", block_key(text_block))
    page.goto(url_of(character))
    expect(page.locator(TEXT)).to_have_text("texto")
    saved(page, lambda: type_at_end(page, " ok"), "texto ok")


def test_page_works_without_local_storage(page, live_server, logged_in, character, text_block):
    page.add_init_script("""
        Object.defineProperty(window, "localStorage", {get() { throw new Error("bloqueado"); }});
    """)
    page.goto(url_of(character))
    saved(page, lambda: type_at_end(page, " ok"), "texto ok")


# Aba vazia

def test_empty_tab_offline_draft_creates_the_block_after_reload(page, context, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    page.goto(url_of(empty))
    context.set_offline(True)
    page.locator(TEXT).click(); page.keyboard.type("primeira linha")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    # Voltar a rede já dispara o reenvio: ele pode chegar antes, depois ou durante o recarregamento.
    context.set_offline(False); page.reload()
    expect(page.locator(TEXT)).to_contain_text("primeira linha")
    wait_no_drafts(page)
    assert read_db(page, lambda: block_of(empty).content) == doc("primeira linha")
    assert read_db(page, Block.objects.filter(tab__record=empty).count) == 1


def test_empty_tab_draft_moves_to_the_new_block(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab_key = f"rascunho:/abas/{empty.tab_set.order_by('position', 'id').first().id}/blocos/"
    held = []
    page.route(BLOCK_SAVE, lambda route: held.append(route))
    page.goto(url_of(empty))
    page.locator(TEXT).click(); page.keyboard.type("oi")
    assert draft(page, tab_key)["version"] is None
    page.wait_for_timeout(1200)
    assert held
    block = block_of(empty)
    assert draft(page, tab_key) is None
    assert draft(page, block_key(block))["version"] == 1


def test_lost_create_answer_does_not_duplicate_the_block(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    lose_answers(page, BLOCK_CREATE)
    page.goto(url_of(empty))
    page.locator(TEXT).click(); page.keyboard.type("sem duplicar")
    expect(page.get_by_text("Salvo")).to_be_visible(timeout=RETRIED)
    assert Block.objects.filter(tab__record=empty).count() == 1
    assert block_of(empty).content == doc("sem duplicar")


def test_draft_from_a_created_block_whose_answer_was_lost_is_recovered(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab = empty.tab_set.order_by("position", "id").first()
    Block.objects.create(tab=tab, kind="text", content={"type": "doc", "content": []})
    seed_draft(page, f"rascunho:/abas/{tab.id}/blocos/", doc("quase perdi"), None)
    with page.expect_response(BLOCK_SAVE):
        page.goto(url_of(empty))
    expect(page.locator(TEXT)).to_have_text("quase perdi")
    expect(page.get_by_text("Salvo")).to_be_visible()
    assert block_of(empty).content == doc("quase perdi")
    assert draft(page, f"rascunho:/abas/{tab.id}/blocos/") is None


def test_tab_draft_against_text_from_another_device_is_a_conflict(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab = empty.tab_set.order_by("position", "id").first()
    Block.objects.create(tab=tab, kind="text", content=doc("do pc"), version=2)
    seed_draft(page, f"rascunho:/abas/{tab.id}/blocos/", doc("do celular"), None)
    page.goto(url_of(empty))
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    response = saved(page, lambda: use(page, MINE), "do celular")
    assert json.loads(response.request.post_data)["version"] == 2
    assert draft(page, f"rascunho:/abas/{tab.id}/blocos/") is None


def test_two_devices_filling_an_empty_tab_conflict(page, live_server, logged_in, campaign):
    empty = make_record(campaign, "Personagens", "Dorn")
    tab = empty.tab_set.order_by("position", "id").first()
    page.goto(url_of(empty))
    Block.objects.create(tab=tab, kind="text", content=doc("do pc"), version=2)
    page.locator(TEXT).click(); page.keyboard.type("do celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    assert Block.objects.filter(tab=tab).count() == 1
    assert block_of(empty).content == doc("do pc")
    page.reload()
    expect(page.get_by_text(CONFLICT)).to_be_visible()


# Documento que o editor não abre

UNREADABLE = [
    {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "antes"}, {"type": "text", "text": ""}]}]},
    {"type": "doc", "content": [{"type": "text", "text": "solto"}]},
]


@pytest.mark.parametrize("content", UNREADABLE, ids=["empty-text-node", "text-outside-paragraph"])
def test_unreadable_doc_stays_read_only_and_is_never_saved(page, live_server, logged_in, character, content):
    set_body(character, content)
    posts = []
    page.on("request", lambda r: posts.append(r.url) if BLOCK_SAVE.search(r.url) else None)
    page.goto(url_of(character))
    expect(page.get_by_text("não abriu no editor")).to_be_visible()
    expect(page.locator(".unreadable")).to_contain_text(content["content"][0].get("text", "antes"))
    expect(page.locator(TEXT)).to_have_attribute("contenteditable", "false")
    page.wait_for_timeout(1200)
    assert not posts
    block = block_of(character)
    assert block.content == content and block.version == 1


def test_draft_is_not_applied_over_an_unreadable_doc(page, live_server, logged_in, character, text_block):
    set_body(character, UNREADABLE[1])
    seed_draft(page, block_key(text_block), doc("rascunho"), 1)
    page.goto(url_of(character))
    expect(page.get_by_text("não abriu no editor")).to_be_visible()
    page.wait_for_timeout(1200)
    assert block_of(character).content == UNREADABLE[1]
    assert draft(page, block_key(text_block)) is not None


def test_long_field_keeps_read_only_when_unreadable(page, live_server, logged_in, character):
    key = field_key(character, "Resumo")
    character.fields = {key: UNREADABLE[1]}
    character.save()
    page.goto(url_of(character))
    expect(page.get_by_text("não abriu no editor")).to_be_visible()
    expect(page.locator(FIELD)).to_have_attribute("contenteditable", "false")


# Campos básicos

def test_short_field_edits_and_saves_with_its_version(page, live_server, logged_in, character):
    key = field_key(character, "Ocupação")
    character.fields = {key: "Ladino"}
    character.field_versions = {key: 4}
    character.save()
    page.goto(url_of(character))
    box = page.get_by_label("Ocupação")
    expect(box).to_have_value("Ladino")
    response = saved(page, lambda: box.fill("Bardo"), "Bardo")
    assert json.loads(response.request.post_data) == {"key": key, "version": 4, "value": "Bardo"}
    assert response.json()["version"] == 5
    assert saved(page, lambda: box.fill("Mago"), "Mago").json()["version"] == 6
    character.refresh_from_db()
    assert character.fields[key] == "Mago"


def test_number_and_link_fields_are_editable(page, live_server, logged_in, campaign):
    hero = make_record(campaign, "Personagens", "Kael")
    track = make_record(campaign, "Trilhas", "Tema")
    page.goto(url_of(hero))
    box = page.get_by_label("Idade")
    assert box.get_attribute("inputmode") == "decimal"
    saved(page, lambda: box.fill(" 34 "), '"34"')
    page.goto(url_of(track))
    saved(page, lambda: page.get_by_label("Link").fill("https://exemplo.com/a"), "exemplo.com")
    hero.refresh_from_db(); track.refresh_from_db()
    assert hero.fields[field_key(hero, "Idade")] == "34"
    assert track.fields[field_key(track, "Link")] == "https://exemplo.com/a"


def test_field_touch_target_and_font(page, live_server, logged_in, character):
    page.goto(url_of(character))
    box = page.get_by_label("Ocupação")
    assert box.bounding_box()["height"] >= 44
    assert box.evaluate("el => getComputedStyle(el).fontSize") == "16px"


def test_invalid_number_is_refused_visibly_and_then_fixed(page, live_server, logged_in, character):
    key = field_key(character, "Idade")
    character.fields = {key: "34"}
    character.save()
    page.goto(url_of(character))
    box = page.get_by_label("Idade")
    box.fill("muito")
    expect(page.get_by_text("Não foi possível salvar. Número inválido.")).to_be_visible()
    character.refresh_from_db()
    assert character.fields[key] == "34"
    assert saved(page, lambda: box.fill("35")).status == 200
    expect(page.get_by_text("Não foi possível salvar")).to_have_count(0)


def test_field_draft_survives_offline_and_is_per_key(page, context, live_server, logged_in, character):
    url = f"/r/{character.id}/campos/"
    key = field_key(character, "Ocupação")
    page.goto(url_of(character))
    context.set_offline(True)
    page.get_by_label("Ocupação").fill("Ferreiro")
    expect(page.get_by_text("Sem conexão")).to_be_visible(timeout=RETRIED)
    assert draft(page, f"rascunho:{url}:{key}")["value"] == "Ferreiro"
    context.set_offline(False); page.reload()
    expect(page.get_by_label("Ocupação")).to_have_value("Ferreiro")
    expect(page.get_by_label("Idade")).to_have_value("")
    wait_no_drafts(page)
    read_db(page, character.refresh_from_db)
    assert character.fields[key] == "Ferreiro"


def test_field_conflict_shows_both_and_uses_the_new_version(page, live_server, logged_in, character):
    key = field_key(character, "Ocupação")
    page.goto(url_of(character))
    assert save_field(character, key, "Bardo", 1).ok
    page.get_by_label("Ocupação").fill("Mago")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_role("group", name=MINE)).to_contain_text("Mago")
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("Bardo")
    response = saved(page, lambda: use(page, MINE), "Mago")
    assert json.loads(response.request.post_data)["version"] == 2
    expect(page.get_by_label("Ocupação")).to_have_value("Mago")
    expect(page.get_by_label("Ocupação")).to_be_editable()


def test_older_field_draft_goes_to_the_conflict_screen(page, live_server, logged_in, character):
    key = field_key(character, "Ocupação")
    assert save_field(character, key, "Bardo", 1).ok
    seed_draft(page, f"rascunho:/r/{character.id}/campos/:{key}", "Mago", 1)
    page.goto(url_of(character))
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    page.wait_for_timeout(1200)
    character.refresh_from_db()
    assert character.fields[key] == "Bardo"


def test_long_field_draft_and_block_draft_do_not_mix(page, live_server, logged_in, character, text_block):
    key = field_key(character, "Resumo")
    seed_draft(page, f"rascunho:/r/{character.id}/campos/:{key}", doc("do resumo"), 1)
    with page.expect_response(FIELD_SAVE):
        page.goto(url_of(character))
    expect(page.locator(FIELD)).to_have_text("do resumo")
    expect(page.locator(TEXT)).to_have_text("texto")


def test_long_field_conflict_with_old_plain_text_shows_it(page, live_server, logged_in, character):
    key = field_key(character, "Resumo")
    page.goto(url_of(character))
    assert save_field(character, key, "texto antigo", 1).ok
    type_at_end(page, "novo", FIELD)
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    expect(page.get_by_role("group", name=THEIRS)).to_contain_text("texto antigo")
    response = saved(page, lambda: use(page, THEIRS), "texto antigo")
    assert json.loads(response.request.post_data)["value"]["type"] == "doc"
    expect(page.locator(FIELD)).to_have_text("texto antigo")


def test_no_horizontal_scroll_during_a_conflict(page, live_server, logged_in, character, text_block):
    page.goto(url_of(character)); save_block(text_block, doc("x" * 400), 1)
    type_at_end(page, " celular")
    expect(page.get_by_text(CONFLICT)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    for button in page.get_by_role("button", name="Usar esta").all():
        assert button.bounding_box()["height"] >= 44
