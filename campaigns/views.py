from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from .access import get_campaign
from .defaults import seed_campaign
from .forms import CampaignForm
from .models import Campaign, RecordType


@login_required
def root(request):
    last = (Campaign.objects.filter(owner=request.user, last_opened_at__isnull=False)
            .order_by("-last_opened_at").first())
    return redirect("campaign-home", campaign_id=last.id) if last else redirect("campaign-list")


@login_required
def campaign_list(request):
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        c.owner = request.user
        c.save()
        seed_campaign(c)
        return redirect("campaign-home", campaign_id=c.id)
    campaigns = Campaign.objects.filter(owner=request.user).order_by("name")
    return render(request, "campaigns/list.html", {"campaigns": campaigns, "form": form})


@login_required
def campaign_home(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    campaign.last_opened_at = timezone.now()
    campaign.save(update_fields=["last_opened_at"])
    types = campaign.recordtype_set.order_by("position")
    if hasattr(RecordType, "record_set"):  # relação criada na Tarefa 3
        types = types.annotate(total=Count("record"))
    return render(request, "campaigns/home.html", {"campaign": campaign, "types": types})
