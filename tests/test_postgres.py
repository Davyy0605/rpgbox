"""Corridas reais entre pedidos paralelos. Só rodam em Postgres (SQLite serializa e esconde tudo isso)."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection, connections

from records.services import add_record_tab
from indexing.models import SearchEntry
from indexing.services import reindex_record
from records.models import Block, Tab
from records.save import first_text_block, save_block

from .helpers import doc, doc_headings
from .test_indexing import make_record

pytestmark = [
    pytest.mark.skipif(connection.vendor != "postgresql", reason="precisa de Postgres"),
    pytest.mark.django_db(transaction=True),
]


def parallel(fn, args):
    gate = Barrier(len(args))

    def run(a):
        try:
            connection.ensure_connection()  # conexão pronta antes da largada
            gate.wait()
            return fn(a)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(len(args)) as pool:
        return list(pool.map(run, args))


@pytest.fixture
def record(user, make_campaign):
    return make_record(make_campaign(user), "Personagens", "Kael", body="texto")


def entries(record):
    return sorted(SearchEntry.objects.filter(record=record).values_list("kind", "anchor"))


def test_same_version_saves_have_one_winner(record):
    block = Block.objects.get(tab__record=record)
    results = parallel(lambda i: save_block(Block.objects.get(pk=block.pk), doc(f"v{i}"), 1), range(6))
    assert sum(r.ok for r in results) == 1
    assert Block.objects.get(pk=block.pk).version == 2
    assert entries(record) == [("record", "")]


def test_blocks_of_one_record_saved_together_do_not_duplicate_index(record):
    blocks = [Block.objects.get(tab__record=record)]
    for n in range(3):
        tab = add_record_tab(record, f"Aba {n}")
        blocks.append(Block.objects.create(tab=tab, kind="text", content=doc("x")))
    for _ in range(20):
        parallel(lambda b: save_block(Block.objects.get(pk=b.pk), doc_headings((2, "t", "Título")), b.version), blocks)
        for b in blocks:
            b.refresh_from_db()
    assert entries(record) == [("heading", "t")] * 4 + [("record", "")]


def test_first_text_block_creates_only_one(user, make_campaign):
    record = make_record(make_campaign(user), "Personagens", "Lia")
    tab = Tab.objects.create(record=record, title="Vazia", position=9)
    results = parallel(lambda _: first_text_block(Tab.objects.get(pk=tab.pk)), range(6))
    assert sum(created for _, created in results) == 1
    assert Block.objects.filter(tab=tab).count() == 1


def test_long_anchor_does_not_break_reindex(record):
    Block.objects.filter(tab__record=record).update(content=doc_headings((2, "a" * 64, "Título")))
    reindex_record(record)
    assert ("heading", "a" * 64) in entries(record)


def test_jsonb_roundtrip(record):
    block = Block.objects.get(tab__record=record)
    save_block(block, doc("ação ☃ \"aspas\""), 1)
    assert Block.objects.get(pk=block.pk).content == doc("ação ☃ \"aspas\"")


def test_concurrent_reindex_does_not_duplicate(record):
    for _ in range(20):
        parallel(lambda _: reindex_record(record), range(6))
        assert entries(record) == [("record", "")]
