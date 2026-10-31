from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from campaigns.access import get_campaign, get_record
from campaigns.models import Campaign

from .copying import copy_record
from .tracks import create_tracks, parse_bulk_tracks

MAX_PASTE = 100_000


@login_required
@require_http_methods(["GET", "POST"])
def record_copy(request, record_id):
    record = get_record(request.user, record_id)
    options = Campaign.objects.filter(owner=request.user).exclude(pk=record.campaign_id).order_by("name")
    if request.method == "POST":
        try:
            dest = get_object_or_404(options, pk=int(request.POST.get("campaign", "")))
        except ValueError:
            raise Http404
        return redirect("record-detail", record_id=copy_record(record, dest).id)
    return render(request, "transfer/copy.html", {"record": record, "campaign": record.campaign, "options": options})


@login_required
@require_http_methods(["GET", "POST"])
def tracks_bulk(request, campaign_id, type_id):
    campaign = get_campaign(request.user, campaign_id)
    rtype = get_object_or_404(campaign.recordtype_set, pk=type_id)
    link = rtype.fielddef_set.filter(kind="link", removed=False).order_by("position", "id").first()
    if link is None:
        raise Http404
    ctx = {"campaign": campaign, "rtype": rtype, "done": None}
    if request.method == "POST":
        text = request.POST.get("text", "")
        if len(text) > MAX_PASTE:
            return HttpResponseBadRequest("Texto grande demais.")
        tracks, bad = parse_bulk_tracks(text)
        ctx.update(done=create_tracks(rtype, link.key, tracks), bad=bad, text="\n".join(
            line for n, line in enumerate(text.splitlines(), start=1) if n in bad))
    return render(request, "transfer/bulk_tracks.html", ctx)
