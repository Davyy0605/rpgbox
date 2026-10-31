import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from campaigns.access import get_block, get_campaign, get_record, get_tab
from content.doc import SEP, as_doc, headings, safe_href
from content.render import editor_doc, render_doc
from campaigns.models import ListGroup

from indexing.services import citations, resolver_for

from .forms import GroupChoiceForm, RecordForm, RenameForm, TitleForm
from .models import Record
from .sections import find_section
from .save import (add_embed, add_text_block, delete_block, delete_preview, rename_record, resolve_embed,
                   save_block, save_field)
from .services import add_record_tab, add_subtab, create_record, visible_fields, visible_tabs


def _type(user, campaign_id, type_id):
    campaign = get_campaign(user, campaign_id)
    return campaign, get_object_or_404(campaign.recordtype_set, pk=type_id)


@login_required
def record_list(request, campaign_id, type_id):
    campaign, rtype = _type(request.user, campaign_id, type_id)
    groups = list(rtype.listgroup_set.order_by("position", "id"))
    records = rtype.record_set.select_related("main_image").order_by("name")
    current = None
    g = request.GET.get("g", "")
    if g:
        current = next((x for x in groups if str(x.id) == g), None)
        if current is None:
            raise Http404
        records = records.filter(group=current)
    link = rtype.fielddef_set.filter(kind="link", removed=False).order_by("position", "id").first()
    return render(request, "records/list.html", {
        "campaign": campaign, "rtype": rtype, "records": _with_copy_links(records, link), "groups": groups,
        "current_group": current, "gallery": request.GET.get("v") == "galeria",
        "has_link": link is not None, "panel": _requested_panel(request, campaign),
        "crumb_url": reverse("record-list", args=[campaign.id, rtype.id]),
    })


@login_required
def record_new(request, campaign_id, type_id):
    campaign, rtype = _type(request.user, campaign_id, type_id)
    form = RecordForm(rtype, request.POST or None, initial={"group": request.GET.get("g")})
    if request.method == "POST" and form.is_valid():
        record = create_record(rtype, form.cleaned_data["name"], form.cleaned_data["group"])
        return redirect("record-detail", record_id=record.id)
    return render(request, "records/new.html", {"campaign": campaign, "rtype": rtype, "form": form})


@login_required
@require_POST
def group_add(request, campaign_id, type_id):
    _, rtype = _type(request.user, campaign_id, type_id)
    form = TitleForm({"title": request.POST.get("name", "").strip()})
    if not form.is_valid():
        return redirect("record-list", campaign_id=campaign_id, type_id=type_id)
    last = rtype.listgroup_set.order_by("-position").first()
    group = ListGroup.objects.create(record_type=rtype, name=form.cleaned_data["title"],
                                     position=(last.position + 1) if last else 0)
    return redirect(f"/c/{campaign_id}/t/{type_id}/?g={group.id}")


@login_required
def record_detail(request, record_id):
    record = get_record(request.user, record_id)
    tabs = visible_tabs(record)
    selected_key = request.GET.get("aba", "")
    passage = request.GET.get("trecho", "")
    found, found_tab = find_section(record, passage) if passage else (None, None)
    if found_tab and not selected_key:
        selected_key = str(found_tab)
    gallery = selected_key == "galeria"
    selected = parent = None
    if not gallery:
        for t in tabs:
            for cand in [t, *t.children]:
                if str(cand.id) == selected_key:
                    selected, parent = cand, t
        if selected is None and tabs:
            selected = parent = tabs[0]
    blocks = _block_views(selected, record) if selected is not None and not gallery else []
    assets = record.asset_set.all()
    scope_tab = None if gallery or selected is None else selected.id
    return render(request, "records/detail.html", {
        "images": [a for a in assets if a.kind == "image" and a.tab_id == scope_tab],
        "files": [a for a in assets if a.kind != "image" and a.tab_id == scope_tab],
        "upload_tab": scope_tab,
        "blocks": blocks,
        "new_block": _new_block_editor(selected) if selected is not None and not blocks else None,
        "record": record, "campaign": record.campaign, "tabs": tabs, "selected": selected,
        "parent": parent, "gallery": gallery, "citations": citations(record), "fields": _detail_fields(record),
        "group_form": GroupChoiceForm(record.record_type, initial={"group": record.group_id}),
        "panel": _requested_panel(request, record.campaign), **_crumb(record, passage, found),
    })


@login_required
def record_panel(request, record_id):
    record = get_record(request.user, record_id)
    return render(request, "records/_panel.html", {"panel": _panel(record, request.GET.get("ancora", ""))})


@login_required
@require_POST
def record_group(request, record_id):
    record = get_record(request.user, record_id)
    form = GroupChoiceForm(record.record_type, request.POST)
    if form.is_valid():
        record.group = form.cleaned_data["group"]
        record.save(update_fields=["group", "updated_at"])
    return redirect("record-detail", record_id=record.id)


@login_required
@require_POST
def tab_add(request, record_id):
    record = get_record(request.user, record_id)
    form = TitleForm({"title": request.POST.get("title", "").strip()})
    if not form.is_valid():
        return redirect("record-detail", record_id=record.id)
    tab = add_record_tab(record, form.cleaned_data["title"])
    return redirect(f"/r/{record.id}/?aba={tab.id}")


@login_required
@require_POST
def subtab_add(request, record_id, tab_id):
    record = get_record(request.user, record_id)
    parent = get_object_or_404(record.tab_set, pk=tab_id)
    form = TitleForm({"title": request.POST.get("title", "").strip()})
    if not form.is_valid() or parent.parent_id:
        return redirect(f"/r/{record.id}/?aba={parent.id}")
    sub = add_subtab(parent, form.cleaned_data["title"])
    return redirect(f"/r/{record.id}/?aba={sub.id}")


def _with_copy_links(records, link):
    records = list(records)
    for r in records:
        value = r.fields.get(link.key) if link else None
        r.copy_link = value if safe_href(value) else None
    return records


def _crumb(record, anchor, found):
    url = reverse("record-detail", args=[record.id])
    if found is None:
        return {"crumb": record.name, "crumb_url": url}
    return {"crumb": f"{record.name}{SEP}{dict(headings(found))[anchor]}", "crumb_url": f"{url}?trecho={anchor}#{anchor}"}


def _panel(record, anchor):
    found = find_section(record, anchor)[0] if anchor else None
    panel = {"record": record, "src": reverse("record-panel", args=[record.id]), **_crumb(record, anchor, found)}
    if found is None:
        return {**panel, "fields": _display_fields(record)}
    return {**panel, "src": f"{panel['src']}?ancora={anchor}", "section": render_doc(found, resolver_for(record.campaign))}


def _requested_panel(request, campaign):
    """Painel de `?painel=`: id inválido ou fora da campanha é ignorado, sem revelar se existe."""
    try:
        record = get_record(request.user, int(request.GET.get("painel", "")))
    except (ValueError, Http404):
        return None
    return _panel(record, request.GET.get("ancora", "")) if record.campaign_id == campaign.id else None


def _display_fields(record):
    resolver = resolver_for(record.campaign)
    return [(f, render_doc(v, resolver) if f.kind == "long" and isinstance(v, dict) else v)
            for f, v in visible_fields(record)]


def _editor(kind, doc, resolver, doc_id, label, **attrs):
    content, missing = editor_doc(as_doc(doc), resolver)
    return {"kind": kind, "doc": content, "doc_id": doc_id, "label": label,
            "missing": ",".join(map(str, missing)), **attrs}


def _detail_fields(record):
    resolver = resolver_for(record.campaign)
    out = []
    for f, value in visible_fields(record):
        item = {"label": f.label, "value": value}
        if f.kind == "long":
            item["editor"] = _editor("field", value, resolver, f"campo-{f.id}", f.label, key=f.key,
                                     save_url=reverse("field-save", args=[record.id]),
                                     version=record.field_versions.get(f.key, 1))
        elif f.kind == "link" and safe_href(value):
            item["href"] = value
        out.append(item)
    return out


def _new_block_editor(tab):
    return _editor("text", None, None, f"aba-{tab.id}", "Texto", create_url=reverse("block-add", args=[tab.id]))


def _block_views(tab, record):
    resolver = resolver_for(record.campaign)
    out = []
    for b in tab.block_set.order_by("position", "id"):
        if b.kind == "embed":
            out.append({"block": b, "embed": resolve_embed(b)})
        else:
            out.append({"block": b, "editor": _editor("text", b.content, resolver, f"bloco-{b.id}", "Texto",
                                                      save_url=reverse("block-save", args=[b.id]),
                                                      version=b.version)})
    return out


def _json_body(request):
    try:
        data = json.loads(request.body)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _version(data):
    v = data.get("version")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


@login_required
@require_POST
def block_add(request, tab_id):
    tab = get_tab(request.user, tab_id)
    block = add_text_block(tab)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"save_url": reverse("block-save", args=[block.id]), "version": block.version})
    return redirect(f"/r/{tab.record_id}/?aba={tab.id}")


@login_required
@require_POST
def embed_add(request, tab_id):
    tab = get_tab(request.user, tab_id)
    try:
        target_id = int(request.POST.get("record", ""))
    except ValueError:
        return HttpResponseBadRequest("Registro inválido.")
    target = get_object_or_404(Record, pk=target_id, campaign_id=tab.record.campaign_id)
    try:
        add_embed(tab, target, request.POST.get("anchor", "").strip())
    except ValidationError:
        return HttpResponseBadRequest("Origem inválida.")
    return redirect(f"/r/{tab.record_id}/?aba={tab.id}")


@login_required
@require_POST
def block_save(request, block_id):
    block = get_block(request.user, block_id)
    data = _json_body(request)
    version = _version(data) if data is not None else None
    if version is None or block.kind != "text":
        return JsonResponse({"error": "Requisição inválida."}, status=400)
    try:
        result = save_block(block, data.get("content"), version)
    except ValidationError:
        return JsonResponse({"error": "Documento inválido."}, status=400)
    if not result.ok:
        return JsonResponse({"version": result.version, "content": result.current_content}, status=409)
    return JsonResponse({"version": result.version})


@login_required
@require_POST
def block_delete(request, block_id):
    block = get_block(request.user, block_id)
    tab = block.tab
    delete_block(block)
    return redirect(f"/r/{tab.record_id}/?aba={tab.id}")


@login_required
@require_POST
def field_save(request, record_id):
    record = get_record(request.user, record_id)
    data = _json_body(request)
    version = _version(data) if data is not None else None
    if version is None or not isinstance(data.get("key"), str):
        return JsonResponse({"error": "Requisição inválida."}, status=400)
    try:
        result = save_field(record, data["key"], data.get("value"), version)
    except ValidationError:
        return JsonResponse({"error": "Valor inválido."}, status=400)
    if not result.ok:
        return JsonResponse({"version": result.version, "value": result.current_content}, status=409)
    return JsonResponse({"version": result.version})


@login_required
@require_POST
def record_rename(request, record_id):
    record = get_record(request.user, record_id)
    form = RenameForm({"name": request.POST.get("name", "").strip()})
    if form.is_valid():
        rename_record(record, form.cleaned_data["name"])
    return redirect("record-detail", record_id=record.id)


@login_required
def record_delete(request, record_id):
    record = get_record(request.user, record_id)
    if request.method == "POST":
        rtype_id, campaign_id = record.record_type_id, record.campaign_id
        record.delete()
        return redirect("record-list", campaign_id=campaign_id, type_id=rtype_id)
    return render(request, "records/delete.html", {
        "record": record, "campaign": record.campaign, "uses": delete_preview(record)})
