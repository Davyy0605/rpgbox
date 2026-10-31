"""Exportação legível de uma campanha: zip com Markdown e arquivos. Não há importação."""
import re
import zipfile

from django.core.files.storage import default_storage

from assets.models import Asset
from content.markdown import doc_to_markdown
from records.models import Block, Record, Tab
from records.sections import section

_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


def safe_name(value, fallback="sem-nome"):
    name = _UNSAFE.sub(" ", value or "")
    name = re.sub(r"\.{2,}", ".", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:100].strip(" .") or fallback


class _Names:
    """Nomes únicos (sem diferenciar maiúsculas) dentro de uma pasta."""

    def __init__(self):
        self.used = set()

    def get(self, value, fallback="sem-nome"):
        base = safe_name(value, fallback)
        name, n = base, 1
        while name.lower() in self.used:
            n += 1
            name = f"{base} ({n})"
        self.used.add(name.lower())
        return name

    def get_file(self, value):
        base = safe_name(value, "arquivo")
        stem, dot, ext = base.rpartition(".")
        if not dot or not stem:
            stem, ext = base, ""
        else:
            ext = "." + ext
        name, n = base, 1
        while name.lower() in self.used:
            n += 1
            name = f"{stem} ({n}){ext}"
        self.used.add(name.lower())
        return name


def _block_text(block):
    if block.kind == "text":
        return doc_to_markdown(block.content).strip() if isinstance(block.content, dict) else ""
    target = block.embed_record
    if target is None:
        return f"> ~~{block.embed_label}~~ (registro removido)"
    parts = []
    for b in Block.objects.filter(tab__record=target, kind="text").order_by("tab__position", "tab_id", "position", "id"):
        if not isinstance(b.content, dict):
            continue
        content = section(b.content, block.embed_anchor) if block.embed_anchor else b.content
        if content is not None:
            parts.append(doc_to_markdown(content).strip())
            if block.embed_anchor:
                break
    body = "\n\n".join(p for p in parts if p)
    quoted = "\n".join(f"> {line}" for line in body.splitlines())
    return f"> **{target.name}**\n{quoted}" if quoted else f"> **{target.name}**"


def _tab_markdown(tab, level, blocks_by_tab, children):
    out = [f"{'#' * level} {tab.title}"]
    for block in blocks_by_tab.get(tab.id, []):
        text = _block_text(block)
        if text:
            out.append(text)
    for sub in children.get(tab.id, []):
        out.append(_tab_markdown(sub, level + 1, blocks_by_tab, children))
    return "\n\n".join(out)


def _record_markdown(record):
    lines = [f"# {record.name}"]
    fields = [f for f in record.record_type.fielddef_set.filter(removed=False).order_by("position", "id")]
    rows = []
    for f in fields:
        value = (record.fields or {}).get(f.key)
        if value not in (None, ""):
            rows.append(f"- **{f.label}:** {str(value).replace(chr(10), ' ')}")
    if rows:
        lines.append("\n".join(rows))
    tabs = list(Tab.objects.filter(record=record).order_by("position", "id"))
    blocks_by_tab = {}
    for b in Block.objects.filter(tab__record=record).select_related("embed_record").order_by("position", "id"):
        blocks_by_tab.setdefault(b.tab_id, []).append(b)
    children = {}
    for t in tabs:
        if t.parent_id:
            children.setdefault(t.parent_id, []).append(t)
    for t in tabs:
        if not t.parent_id:
            lines.append(_tab_markdown(t, 2, blocks_by_tab, children))
    return "\n\n".join(lines) + "\n"


def write_export(campaign, fileobj) -> None:
    records = (Record.objects.filter(campaign=campaign)
               .select_related("record_type").order_by("record_type__position", "record_type_id", "id"))
    type_names = _Names()
    type_dirs = {}
    record_names = {}
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_DEFLATED) as zf:
        for record in records:
            tid = record.record_type_id
            if tid not in type_dirs:
                type_dirs[tid] = type_names.get(record.record_type.name, "Sem tipo")
                record_names[tid] = _Names()
            folder = f"{type_dirs[tid]}/{record_names[tid].get(record.name)}"
            zf.writestr(f"{folder}/registro.md", _record_markdown(record))
            file_names = _Names()
            for asset in Asset.objects.filter(record=record).order_by("created_at", "id"):
                target = f"{folder}/arquivos/{file_names.get_file(asset.filename)}"
                try:
                    with default_storage.open(asset.key, "rb") as src, \
                            zf.open(zipfile.ZipInfo(target), "w") as dst:
                        _copy(src, dst)
                except Exception:
                    continue


def _copy(src, dst):
    while chunk := src.read(1024 * 1024):
        dst.write(chunk)
