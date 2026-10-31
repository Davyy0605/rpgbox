import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from content.doc import clean_text, safe_href, valid_anchor, validate_doc
from content.render import render_doc
from indexing.services import citations, reindex_record, resolver_for

from .models import Block, Record, Tab
from .sections import section

MAX_VALUE = 2000
NUMBER_RE = re.compile(r"-?[0-9]+(?:[.,][0-9]+)?")


@dataclass
class SaveResult:
    ok: bool
    version: int
    current_content: object = None


@dataclass
class EmbedView:
    record: Record | None
    html: str
    missing: bool
    label: str


def save_block(block, content, base_version) -> SaveResult:
    """Salva o texto se `base_version` ainda é a do servidor; senão devolve o texto atual."""
    clean = validate_doc(content)
    with transaction.atomic():
        locked = Block.objects.select_for_update().select_related("tab__record").get(pk=block.pk)
        if locked.kind != "text":
            raise ValidationError("Bloco não é de texto.")
        if locked.version != base_version:
            return SaveResult(False, locked.version, locked.content)
        locked.content = clean
        locked.version += 1
        locked.save(update_fields=["content", "version"])
        reindex_record(locked.tab.record)
    block.content, block.version = locked.content, locked.version
    return SaveResult(True, locked.version, locked.content)


def _check_kind(kind, value):
    if value and kind == "number" and not NUMBER_RE.fullmatch(value):
        raise ValidationError("Número inválido.")
    if value and kind == "link" and not safe_href(value):
        raise ValidationError("Endereço inválido.")


def save_field(record, key, value, base_version) -> SaveResult:
    with transaction.atomic():
        locked = Record.objects.select_for_update().select_related("record_type").get(pk=record.pk)
        fdef = locked.record_type.fielddef_set.filter(key=key).first()
        if fdef is None:
            raise ValidationError("Campo inexistente.")
        if fdef.kind == "long" and isinstance(value, dict):
            value = validate_doc(value)
        elif isinstance(value, str) and len(value) <= MAX_VALUE and clean_text(value):
            _check_kind(fdef.kind, value)
        else:
            raise ValidationError("Valor inválido.")
        current = locked.fields.get(key, "")
        server_version = locked.field_versions.get(key, 1)
        if server_version != base_version:
            return SaveResult(False, server_version, current)
        locked.fields = {**locked.fields, key: value}
        locked.field_versions = {**locked.field_versions, key: server_version + 1}
        locked.save(update_fields=["fields", "field_versions", "updated_at"])
        reindex_record(locked)
    record.fields, record.field_versions = locked.fields, locked.field_versions
    return SaveResult(True, server_version + 1, value)


def add_text_block(tab) -> Block:
    last = tab.block_set.aggregate(m=Max("position"))["m"]
    return Block.objects.create(tab=tab, kind="text", position=(last or 0) + 1,
                                content={"type": "doc", "content": []})


def first_text_block(tab) -> tuple[Block, bool]:
    """O bloco que o editor de uma aba vazia preenche, e se ele nasceu agora.

    O pedido é repetido quando a resposta se perde, e repetir não pode criar outro bloco.
    """
    with transaction.atomic():
        Tab.objects.select_for_update().get(pk=tab.pk)
        existing = tab.block_set.filter(kind="text").order_by("position", "id").first()
        return (existing, False) if existing else (add_text_block(tab), True)


def add_embed(tab, target_record, anchor) -> Block:
    anchor = anchor or ""
    if anchor and not valid_anchor(anchor):
        raise ValidationError("Âncora inválida.")
    if target_record.campaign_id != tab.record.campaign_id:
        raise ValidationError("Origem de outra campanha.")
    if target_record.id == tab.record_id:
        raise ValidationError("Um registro não pode incorporar a si mesmo.")
    with transaction.atomic():
        last = tab.block_set.aggregate(m=Max("position"))["m"]
        block = Block.objects.create(tab=tab, kind="embed", position=(last or 0) + 1, embed_record=target_record,
                                     embed_anchor=anchor, embed_label=target_record.name[:160])
        reindex_record(tab.record)
    return block


def delete_block(block) -> None:
    record = block.tab.record
    with transaction.atomic():
        block.delete()
        reindex_record(record)


def rename_record(record, name) -> None:
    with transaction.atomic():
        record.name = name
        record.save(update_fields=["name", "updated_at"])
        Block.objects.filter(embed_record=record).update(embed_label=name[:160])
        reindex_record(record)


def delete_preview(record) -> int:
    """Quantos registros citam ou incorporam este."""
    ids = set(citations(record).values_list("id", flat=True))
    ids |= set(Block.objects.filter(embed_record=record).values_list("tab__record_id", flat=True))
    ids.discard(record.id)
    return len(ids)


def _link(rec_id, name, anchor=""):
    href = reverse("record-detail", args=[rec_id]) + (f"#{anchor}" if anchor else "")
    return format_html('<a class="embed-link" href="{}" data-record="{}">{}</a>', href, rec_id, name)


def resolve_embed(block) -> EmbedView:
    target = block.embed_record
    if target is None:
        return EmbedView(None, "", True, block.embed_label)
    resolver = resolver_for(target.campaign)
    parts = []
    for b in Block.objects.filter(tab__record=target).order_by("tab__position", "tab_id", "position", "id"):
        if b.kind == "embed":
            if block.embed_anchor:
                continue
            if b.embed_record_id:
                parts.append(_link(b.embed_record_id, b.embed_record.name, b.embed_anchor))
            else:
                parts.append(format_html("<p><s>{}</s></p>", b.embed_label))
        elif isinstance(b.content, dict):
            content = section(b.content, block.embed_anchor) if block.embed_anchor else b.content
            if content is not None:
                parts.append(render_doc(content, resolver))
                if block.embed_anchor:
                    break
    return EmbedView(target, mark_safe("".join(parts)), False, target.name)
