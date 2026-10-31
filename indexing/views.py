from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from campaigns.access import get_campaign

from .services import search as run_search
from .services import suggest as run_suggest


@login_required
def search(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    q = request.GET.get("q", "").strip()
    ctx = {"campaign": campaign, "q": q, "results": run_search(campaign, q)}
    template = "indexing/_suggest.html" if request.headers.get("HX-Request") else "indexing/results.html"
    return render(request, template, ctx)


@login_required
def suggest(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    return JsonResponse(run_suggest(campaign, request.GET.get("q", "")), safe=False)
