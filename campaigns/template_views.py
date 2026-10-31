from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from records.forms import TitleForm

from .access import deleted, get_campaign
from .models import FieldDef, ListGroup, RecordType, TabDef


def create_type(campaign, name):
    """Cria um tipo próprio, sem campos e sem abas."""
    last = campaign.recordtype_set.order_by("-position").first()
    return RecordType.objects.create(campaign=campaign, name=name, position=(last.position + 1) if last else 0)


def _owned(queryset, user, pk, path):
    return get_object_or_404(queryset, pk=pk, **{path: user})


def _body(rtype):
    tabs = list(rtype.tabdef_set.filter(removed=False).order_by("position", "id"))
    tops = [t for t in tabs if t.parent_id is None]
    for t in tops:
        t.subs = [s for s in tabs if s.parent_id == t.id]
    return {
        "campaign": rtype.campaign, "rtype": rtype, "kinds": FieldDef.KINDS, "tabs": tops,
        "fields": rtype.fielddef_set.filter(removed=False).order_by("position", "id"),
        "groups": rtype.listgroup_set.order_by("position", "id"),
    }


def template_body(request, rtype):
    return render(request, "campaigns/_template_body.html", _body(rtype))


def _back(request, rtype):
    if "HX-Request" in request.headers:
        return template_body(request, rtype)
    return redirect("template-edit", campaign_id=rtype.campaign_id, type_id=rtype.id)


def _next(qs):
    return (qs.aggregate(m=Max("position"))["m"] or -1) + 1


def _move(siblings, obj, direction):
    """Troca de lugar com o vizinho; renumera a lista para não depender de posições repetidas."""
    items = list(siblings.order_by("position", "id"))
    i = next((n for n, x in enumerate(items) if x.pk == obj.pk), None)
    if i is None:
        return
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    for n, x in enumerate(items):
        if x.position != n:
            x.position = n
            x.save(update_fields=["position"])


def _title(request, key="title"):
    form = TitleForm({"title": request.POST.get(key, "").strip()})
    return form.cleaned_data["title"] if form.is_valid() else None


def _field(user, field_id):
    return _owned(FieldDef.objects.select_related("record_type"), user, field_id, "record_type__campaign__owner")


def _tabdef(user, tabdef_id):
    return _owned(TabDef.objects.select_related("record_type"), user, tabdef_id, "record_type__campaign__owner")


def _group(user, group_id):
    return _owned(ListGroup.objects.select_related("record_type"), user, group_id, "record_type__campaign__owner")


@login_required
def template_edit(request, campaign_id, type_id):
    campaign = get_campaign(request.user, campaign_id)
    rtype = get_object_or_404(campaign.recordtype_set, pk=type_id)
    return render(request, "campaigns/template_edit.html", _body(rtype))


# Campos

@login_required
@require_POST
def field_add(request, type_id):
    rtype = _owned(RecordType.objects.all(), request.user, type_id, "campaign__owner")
    label, kind = _title(request, "label"), request.POST.get("kind")
    if label and kind in dict(FieldDef.KINDS):
        FieldDef.objects.create(record_type=rtype, label=label, kind=kind,
                                position=_next(rtype.fielddef_set))
    return _back(request, rtype)


@login_required
@require_POST
def field_rename(request, field_id):
    f = _field(request.user, field_id)
    label = _title(request, "label")
    if label:
        f.label = label
        f.save(update_fields=["label"])
    return _back(request, f.record_type)


@login_required
@require_POST
def field_move(request, field_id):
    f = _field(request.user, field_id)
    _move(f.record_type.fielddef_set.filter(removed=False), f, request.POST.get("dir"))
    return _back(request, f.record_type)


@login_required
@require_POST
def field_remove(request, field_id):
    f = _field(request.user, field_id)
    f.removed = True
    f.save(update_fields=["removed"])
    return _back(request, f.record_type)


# Abas do modelo

@login_required
@require_POST
def tabdef_add(request, type_id):
    rtype = _owned(RecordType.objects.all(), request.user, type_id, "campaign__owner")
    title = _title(request)
    parent = None
    if request.POST.get("parent"):
        parent = get_object_or_404(rtype.tabdef_set, pk=request.POST["parent"], removed=False)
        if parent.parent_id:
            return HttpResponseBadRequest("Sub-abas têm um único nível.")
    if title:
        TabDef.objects.create(record_type=rtype, parent=parent, title=title, position=_next(rtype.tabdef_set))
    return _back(request, rtype)


@login_required
@require_POST
def tabdef_rename(request, tabdef_id):
    d = _tabdef(request.user, tabdef_id)
    title = _title(request)
    if title:
        d.title = title
        d.save(update_fields=["title"])
    return _back(request, d.record_type)


@login_required
@require_POST
def tabdef_move(request, tabdef_id):
    d = _tabdef(request.user, tabdef_id)
    _move(d.record_type.tabdef_set.filter(parent_id=d.parent_id, removed=False), d, request.POST.get("dir"))
    return _back(request, d.record_type)


@login_required
@require_POST
def tabdef_remove(request, tabdef_id):
    d = _tabdef(request.user, tabdef_id)
    TabDef.objects.filter(pk=d.pk).update(removed=True)
    TabDef.objects.filter(parent=d).update(removed=True)
    return _back(request, d.record_type)


# Sub-abas da lista (adicionar é group-add)

@login_required
@require_POST
def group_rename(request, group_id):
    g = _group(request.user, group_id)
    name = _title(request, "name")
    if name:
        g.name = name
        g.save(update_fields=["name"])
    return _back(request, g.record_type)


@login_required
@require_POST
def group_remove(request, group_id):
    g = _group(request.user, group_id)
    rtype = g.record_type
    g.delete()  # registros ficam sem sub-aba (SET_NULL)
    return deleted(request, _back(request, rtype))
