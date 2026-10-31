import os
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Sum
from django.utils.http import content_disposition_header

from .images import InvalidFile, process_image
from .models import Asset

MAX_BYTES = 25 * 1024 * 1024
TOO_BIG = "O arquivo passa de 25 MB. Escolha um arquivo menor."
BAD_TYPE = "Tipo de arquivo não aceito."

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ZIP_EXTS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
OLE_EXTS = {".doc", ".xls", ".ppt"}
TEXT_EXTS = {".txt", ".md", ".rtf"}
ALLOWED_EXTS = IMAGE_EXTS | ZIP_EXTS | OLE_EXTS | TEXT_EXTS | {".pdf"}
CONTENT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown", ".rtf": "application/rtf"}


def _head(file, n=8):
    file.seek(0)
    head = file.read(n)
    file.seek(0)
    return head


def _validate(file, ext):
    if ext not in ALLOWED_EXTS:
        raise InvalidFile(f"{BAD_TYPE} Use imagens, PDF ou documentos do Office/LibreOffice, txt, md ou rtf.")
    head = _head(file)
    if ext == ".pdf" and not head.startswith(b"%PDF-"):
        raise InvalidFile(f"{BAD_TYPE} O PDF está inválido.")
    if ext in ZIP_EXTS and not head.startswith(b"PK\x03\x04"):
        raise InvalidFile(f"{BAD_TYPE} O conteúdo não confere com a extensão.")
    if ext in OLE_EXTS and not head.startswith(b"\xd0\xcf\x11\xe0"):
        raise InvalidFile(f"{BAD_TYPE} O conteúdo não confere com a extensão.")
    if ext in TEXT_EXTS and b"\x00" in _head(file, 4096):
        raise InvalidFile(f"{BAD_TYPE} O conteúdo não confere com a extensão.")


def store_upload(record, tab, file):
    if file.size > MAX_BYTES:
        raise InvalidFile(TOO_BIG)
    filename = os.path.basename((file.name or "").replace("\\", "/"))[:255] or "arquivo"
    ext = os.path.splitext(filename)[1].lower()
    _validate(file, ext)
    owner_id = record.campaign.owner_id
    base = f"{owner_id}/{uuid.uuid4()}"
    thumb_key = ""
    width = height = None
    if ext in IMAGE_EXTS:
        img = process_image(file)
        data, thumb = img.data, img.thumb
        width, height = img.width, img.height
        kind, content_type = "image", "image/webp"
        key = default_storage.save(base + ".webp", ContentFile(data))
        thumb_key = default_storage.save(base + "_t.webp", ContentFile(thumb))
        size = len(data) + len(thumb)
    else:
        kind = "pdf" if ext == ".pdf" else "file"
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        file.seek(0)
        key = default_storage.save(base + ext, file)
        size = file.size
    with transaction.atomic():
        asset = Asset.objects.create(
            owner_id=owner_id, record=record, tab=tab, kind=kind, filename=filename, key=key,
            thumb_key=thumb_key, content_type=content_type, size=size, width=width, height=height)
        if kind == "image" and record.main_image_id is None:
            record.main_image = asset
            record.save(update_fields=["main_image"])
    return asset


def kind_of_open(asset):
    return "viewer" if asset.kind in ("image", "pdf") else "download"


def asset_url(asset, variant="full", inline=False):
    key = asset.thumb_key if variant == "thumb" and asset.thumb_key else asset.key
    if default_storage.__class__.__name__ == "S3Storage":
        disposition = "inline" if inline else content_disposition_header(True, asset.filename)
        return default_storage.url(key, parameters={"ResponseContentDisposition": disposition,
                                                    "ResponseContentType": asset.content_type})
    return default_storage.url(key)


def storage_used(user):
    return Asset.objects.filter(owner=user).aggregate(t=Sum("size"))["t"] or 0
