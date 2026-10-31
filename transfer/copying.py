import os
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from assets.models import Asset
from campaigns.models import FieldDef, RecordType, TabDef
from indexing.services import reindex_record
from records.models import Block, Record, Tab
from records.sections import section


def strip_mentions(node):
    """Cópia do documento em que menções viram o nome em texto simples."""
    if isinstance(node, list):
        out = [strip_mentions(n) for n in node]
        return [n for n in out if n is not None]
    if not isinstance(node, dict):
        return node
    if node.get("type") == "mention":
        label = (node.get("attrs") or {}).get("label") or ""
        return {"type": "text", "text": label} if label else None
    copy = dict(node)
    if isinstance(copy.get("content"), list):
        copy["content"] = strip_mentions(copy["content"])
    return copy


def _para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}] if text else []}


def _frozen_embed(block):
    """Conteúdo atual do bloco incorporado, como documento editável."""
    target = block.embed_record
    nodes = []
    if target is not None:
        for b in Block.objects.filter(tab__record=target, kind="text").order_by("tab__position", "tab_id", "position", "id"):
            if not isinstance(b.content, dict):
                continue
            content = section(b.content, block.embed_anchor) if block.embed_anchor else b.content
            if content is not None:
                nodes.extend(content.get("content") or [])
                if block.embed_anchor:
                    break
    nodes = strip_mentions(nodes)
    if not nodes:
        nodes = [_para(block.embed_label)] if block.embed_label else []
    return {"type": "doc", "content": nodes}


def _dest_type(source_type, dest):
    existing = dest.recordtype_set.filter(name=source_type.name).first()
    if existing:
        return existing
    last = dest.recordtype_set.order_by("-position").first()
    rtype = RecordType.objects.create(campaign=dest, name=source_type.name,
                                      position=(last.position + 1) if last else 0)
    for f in source_type.fielddef_set.order_by("position", "id"):
        FieldDef.objects.create(record_type=rtype, label=f.label, kind=f.kind, position=f.position, removed=f.removed)
    defs = {}
    for d in sorted(source_type.tabdef_set.order_by("position", "id"), key=lambda d: d.parent_id is not None):
        defs[d.id] = TabDef.objects.create(record_type=rtype, parent=defs.get(d.parent_id), title=d.title,
                                           position=d.position, removed=d.removed)
    return rtype


def _field_map(source_type, dest_type):
    """key de origem -> key no destino, ligando por rótulo; sem par, cria o campo."""
    dest_fields = list(dest_type.fielddef_set.order_by("removed", "position", "id"))
    mapping = {}
    for f in source_type.fielddef_set.order_by("position", "id"):
        match = next((d for d in dest_fields if d.label == f.label), None)
        if match is None:
            match = FieldDef.objects.create(record_type=dest_type, label=f.label, kind=f.kind,
                                            position=len(dest_fields), removed=f.removed)
            dest_fields.append(match)
        mapping[f.key] = match.key
    return mapping


def _tabdef_for(source_def, dest_defs):
    if source_def is None:
        return None
    parent_title = source_def.parent.title if source_def.parent_id else None
    for d in dest_defs:
        if d.title == source_def.title and (d.parent.title if d.parent_id else None) == parent_title:
            return d
    return None


def _copy_asset(asset, owner_id, new_record, tab, saved):
    base = f"{owner_id}/{uuid.uuid4()}"
    ext = os.path.splitext(asset.key)[1]
    with default_storage.open(asset.key, "rb") as f:
        key = default_storage.save(base + ext, ContentFile(f.read()))
    saved.append(key)
    thumb_key = ""
    if asset.thumb_key:
        with default_storage.open(asset.thumb_key, "rb") as f:
            thumb_key = default_storage.save(base + "_t" + os.path.splitext(asset.thumb_key)[1], ContentFile(f.read()))
        saved.append(thumb_key)
    return Asset.objects.create(
        owner_id=owner_id, record=new_record, tab=tab, kind=asset.kind, filename=asset.filename, key=key,
        thumb_key=thumb_key, content_type=asset.content_type, size=asset.size, width=asset.width, height=asset.height)


def copy_record(record, dest) -> Record:
    """Copia o registro para outra campanha do mesmo mestre, de forma independente."""
    saved = []
    try:
        with transaction.atomic():
            source_type = record.record_type
            dest_type = _dest_type(source_type, dest)
            fmap = _field_map(source_type, dest_type)
            fields = {}
            for key, value in (record.fields or {}).items():
                if key in fmap:
                    fields[fmap[key]] = strip_mentions(value) if isinstance(value, dict) else value
            new = Record.objects.create(campaign=dest, record_type=dest_type, name=record.name, fields=fields)

            dest_defs = list(dest_type.tabdef_set.select_related("parent"))
            tab_map = {}
            tabs = sorted(record.tab_set.select_related("tab_def__parent").order_by("position", "id"),
                          key=lambda t: t.parent_id is not None)
            for t in tabs:
                tab_map[t.id] = Tab.objects.create(
                    record=new, tab_def=_tabdef_for(t.tab_def, dest_defs), parent=tab_map.get(t.parent_id),
                    title=t.title, position=t.position)

            for b in Block.objects.filter(tab__record=record).select_related("embed_record").order_by("tab_id", "position", "id"):
                content = _frozen_embed(b) if b.kind == "embed" else strip_mentions(b.content)
                Block.objects.create(tab=tab_map[b.tab_id], kind="text", position=b.position, content=content)

            main = None
            for a in record.asset_set.order_by("created_at"):
                tab = tab_map.get(a.tab_id) if a.tab_id else None
                copy = _copy_asset(a, dest.owner_id, new, tab, saved)
                if record.main_image_id == a.id:
                    main = copy
            if main:
                new.main_image = main
                new.save(update_fields=["main_image"])
            reindex_record(new)
    except Exception:
        for key in saved:
            try:
                default_storage.delete(key)
            except Exception:
                pass
        raise
    return new
