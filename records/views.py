from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from campaigns.access import get_campaign, get_record
from campaigns.models import ListGroup

from .forms import GroupChoiceForm, RecordForm, TitleForm
from .services import add_record_tab, add_subtab, create_record, visible_fields, visible_tabs


def _type(user, campaign_id, type_id):
    campaign = get_campaign(user, campaign_id)
    return campaign, get_object_or_404(campaign.recordtype_set, pk=type_id)


@login_required
def record_list(request, campaign_id, type_id):
    campaign, rtype = _type(request.user, campaign_id, type_id)
    groups = list(rtype.listgroup_set.order_by("position", "id"))
    records = rtype.record_set.order_by("name")
    current = None
    g = request.GET.get("g", "")
    if g:
        current = next((x for x in groups if str(x.id) == g), None)
        if current is None:
            raise Http404
        records = records.filter(group=current)
    return render(request, "records/list.html", {
        "campaign": campaign, "rtype": rtype, "records": records, "groups": groups,
        "current_group": current, "gallery": request.GET.get("v") == "galeria",
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
    gallery = selected_key == "galeria"
    selected = parent = None
    if not gallery:
        for t in tabs:
            for cand in [t, *t.children]:
                if str(cand.id) == selected_key:
                    selected, parent = cand, t
        if selected is None and tabs:
            selected = parent = tabs[0]
    return render(request, "records/detail.html", {
        "record": record, "campaign": record.campaign, "tabs": tabs, "selected": selected,
        "parent": parent, "gallery": gallery, "fields": visible_fields(record),
        "group_form": GroupChoiceForm(record.record_type, initial={"group": record.group_id}),
    })


@login_required
def record_panel(request, record_id):
    record = get_record(request.user, record_id)
    return render(request, "records/_panel.html", {"record": record, "fields": visible_fields(record)})


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
