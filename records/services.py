from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from .models import Block, Record, Tab


def _filled(value):
    return value not in (None, "")


def _sync_tabs(record):
    defs = list(record.record_type.tabdef_set.all())
    tabs = list(record.tab_set.select_related("tab_def"))
    by_def = {t.tab_def_id: t for t in tabs if t.tab_def_id}
    for d in sorted(defs, key=lambda d: d.parent_id is not None):
        tab = by_def.get(d.id)
        if tab is None:
            parent = by_def.get(d.parent_id) if d.parent_id else None
            if d.removed or (d.parent_id and parent is None):
                continue
            tab = Tab.objects.create(record=record, tab_def=d, parent=parent, title=d.title, position=d.position)
            tabs.append(tab)
            by_def[d.id] = tab
        elif (tab.title, tab.position) != (d.title, d.position):
            tab.title, tab.position = d.title, d.position
            tab.save(update_fields=["title", "position"])
    return tabs


@transaction.atomic
def visible_tabs(record):
    """Sincroniza as abas do registro com o modelo e devolve as de topo, com .children."""
    tabs = _sync_tabs(record)
    with_blocks = set(Block.objects.filter(tab__record=record).values_list("tab_id", flat=True))
    by_id = {t.id: t for t in tabs}

    def has_content(tab):
        return tab.id in with_blocks or any(has_content(c) for c in tabs if c.parent_id == tab.id)

    def shown(tab):
        return tab.tab_def is None or not tab.tab_def.removed or has_content(tab)

    for t in tabs:
        t.children = []
    tops = []
    for t in sorted(tabs, key=lambda t: (t.position, t.id)):
        if not shown(t):
            continue
        if t.parent_id is None:
            tops.append(t)
        elif t.parent_id in by_id and shown(by_id[t.parent_id]):
            by_id[t.parent_id].children.append(t)
    return tops


def visible_fields(record):
    out = []
    for f in record.record_type.fielddef_set.order_by("position", "id"):
        value = record.fields.get(f.key, "")
        if not f.removed or _filled(value):
            out.append((f, value))
    return out


def _next_position(record):
    return (record.tab_set.aggregate(m=Max("position"))["m"] or 0) + 1


def add_subtab(tab, title):
    if tab.parent_id:
        raise ValidationError("Sub-abas têm um único nível.")
    return Tab.objects.create(record=tab.record, parent=tab, title=title, position=_next_position(tab.record))


def add_record_tab(record, title):
    return Tab.objects.create(record=record, title=title, position=_next_position(record))


@transaction.atomic
def create_record(record_type, name, group=None):
    record = Record.objects.create(campaign=record_type.campaign, record_type=record_type, name=name, group=group)
    _sync_tabs(record)
    return record
