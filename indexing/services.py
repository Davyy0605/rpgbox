from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from content.doc import SEP, headings, is_int, iter_nodes, plain_text
from records.models import Block, Record

from .models import Link, SearchEntry
from .normalize import normalize


@dataclass
class Result:
    record: Record
    anchor: str
    label: str
    kind: str


def resolver_for(campaign):
    """Resolvedor para render_doc: nomes só de registros desta campanha."""
    def resolve(ids):
        return dict(Record.objects.filter(campaign=campaign, id__in=list(ids)).values_list("id", "name"))
    return resolve


def _docs(record):
    """Documentos de texto do registro: campos longos e blocos de texto."""
    for f in record.record_type.fielddef_set.filter(kind="long"):
        value = record.fields.get(f.key)
        if isinstance(value, dict):
            yield value
        elif isinstance(value, str) and value:
            yield {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": value}]}]}
    for b in Block.objects.filter(tab__record=record, kind="text").order_by("tab__position", "position", "id"):
        if isinstance(b.content, dict):
            yield b.content


@transaction.atomic
def reindex_record(record) -> None:
    # Serializa reindexações do mesmo registro: sem isso, duas apagam o antigo e ambas inserem o novo.
    Record.objects.select_for_update(no_key=True).get(pk=record.pk)
    Link.objects.filter(source_record=record).delete()
    SearchEntry.objects.filter(record=record).delete()
    links, seen, entries, texts = [], set(), [], []
    in_campaign = {}

    def add_link(target_id, anchor, kind):
        if not is_int(target_id) or target_id == record.id:
            return
        if target_id not in in_campaign:
            in_campaign[target_id] = Record.objects.filter(pk=target_id, campaign_id=record.campaign_id).exists()
        key = (target_id, anchor, kind)
        if in_campaign[target_id] and key not in seen:
            seen.add(key)
            links.append(Link(source_record=record, target_record_id=target_id, target_anchor=anchor, kind=kind))

    for d in _docs(record):
        texts.append(plain_text(d))
        for n in iter_nodes(d):
            if n.get("type") == "mention":
                a = n.get("attrs") or {}
                add_link(a.get("record"), a.get("anchor") or "", "mention")
        for anchor, text in headings(d):
            entries.append(SearchEntry(
                campaign_id=record.campaign_id, record=record, anchor=anchor, kind="heading",
                title=f"{record.name}{SEP}{text}"[:300], title_norm=normalize(text)[:300]))
    for b in Block.objects.filter(tab__record=record, kind="embed", embed_record__isnull=False):
        add_link(b.embed_record_id, b.embed_anchor, "embed")
    entries.append(SearchEntry(
        campaign_id=record.campaign_id, record=record, kind="record", title=record.name,
        title_norm=normalize(record.name)[:300], body_norm=normalize(" ".join(t for t in texts if t))))
    Link.objects.bulk_create(links)
    SearchEntry.objects.bulk_create(entries)


def citations(record):
    return Record.objects.filter(links_out__target_record=record).distinct().order_by("name")


def citation_count(record) -> int:
    return citations(record).count()


def _rank(entry, q):
    if entry.kind == "record":
        if entry.title_norm.startswith(q):
            return 0
        return 1 if q in entry.title_norm else 3
    return 2 if q in entry.title_norm else 3


def _find(campaign, q, limit, with_body):
    q = normalize(q).strip()
    if not q:
        return []
    cond = Q(title_norm__contains=q) | (Q(body_norm__contains=q) if with_body else Q())
    entries = SearchEntry.objects.filter(campaign=campaign).filter(cond).select_related("record")
    best = {}
    for e in entries:
        key = (e.record_id, e.anchor)
        rank = _rank(e, q)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, e)
    ordered = sorted(best.values(), key=lambda x: (x[0], normalize(x[1].record.name), x[1].anchor))
    return [e for _, e in ordered[:limit]]


def search(campaign, q, limit=20) -> list[Result]:
    return [Result(e.record, e.anchor, e.title, e.kind) for e in _find(campaign, q, limit, True)]


def suggest(campaign, q, limit=8) -> list[dict]:
    return [{"record": e.record_id, "anchor": e.anchor, "label": e.title} for e in _find(campaign, q, limit, False)]
