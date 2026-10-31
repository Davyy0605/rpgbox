from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from campaigns.access import deleted, get_record

from .images import InvalidFile
from .models import Asset
from .storage import asset_url, kind_of_open, store_upload


def get_asset(user, asset_id):
    return get_object_or_404(Asset.objects.select_related("record__campaign"), pk=asset_id,
                             record__campaign__owner=user)


@login_required
@require_POST
def asset_upload(request, record_id):
    record = get_record(request.user, record_id)
    tab = None
    if request.POST.get("tab"):
        tab = get_object_or_404(record.tab_set.filter(hidden=False), pk=request.POST["tab"])
    file = request.FILES.get("file")
    try:
        if file is None:
            raise InvalidFile("Escolha um arquivo.")
        store_upload(record, tab, file)
    except InvalidFile as e:
        return render(request, "assets/error.html", {"message": str(e), "record": record}, status=400)
    return redirect(f"/r/{record.id}/?aba={tab.id}" if tab else f"/r/{record.id}/?aba=galeria")


@login_required
def asset_open(request, asset_id):
    asset = get_asset(request.user, asset_id)
    if kind_of_open(asset) == "viewer":
        return render(request, "assets/viewer.html", {
            "asset": asset, "file_url": f"/arquivos/{asset.id}/arquivo/?inline=1", "record": asset.record})
    return _serve(asset, inline=False, variant="full")


@login_required
def asset_file(request, asset_id):
    asset = get_asset(request.user, asset_id)
    inline = kind_of_open(asset) == "viewer" and request.GET.get("inline") == "1"
    return _serve(asset, inline, "thumb" if request.GET.get("v") == "thumb" else "full")


def _serve(asset, inline, variant):
    if default_storage.__class__.__name__ == "S3Storage":
        return HttpResponseRedirect(asset_url(asset, variant, inline))
    key = asset.thumb_key if variant == "thumb" and asset.thumb_key else asset.key
    resp = FileResponse(default_storage.open(key), as_attachment=not inline, filename=asset.filename,
                        content_type=asset.content_type or "application/octet-stream")
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def _back(request, record, tab_id):
    if "HX-Request" not in request.headers:
        return redirect(f"/r/{record.id}/?aba={tab_id or 'galeria'}")
    assets = record.asset_set.filter(tab_id=tab_id)
    return render(request, "assets/_items.html", {
        "record": record, "images": [a for a in assets if a.kind == "image"],
        "files": [a for a in assets if a.kind != "image"]})


@login_required
@require_POST
def asset_main(request, asset_id):
    asset = get_asset(request.user, asset_id)
    if asset.kind == "image":
        asset.record.main_image = asset
        asset.record.save(update_fields=["main_image"])
    return _back(request, asset.record, asset.tab_id)


@login_required
@require_POST
def asset_delete(request, asset_id):
    asset = get_asset(request.user, asset_id)
    record, tab_id = asset.record, asset.tab_id
    asset.delete()
    record.refresh_from_db(fields=["main_image"])
    return deleted(request, _back(request, record, tab_id))
