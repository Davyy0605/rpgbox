from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from assets.storage import storage_used

from .access import deleted, get_campaign
from .defaults import seed_campaign
from .forms import CampaignForm, RecordTypeForm
from .models import Campaign
from .template_views import create_type


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
    return render(request, "campaigns/list.html", {"campaigns": campaigns, "form": form,
                                                   "storage_mb": round(storage_used(request.user) / (1024 * 1024), 1)})


@login_required
@ensure_csrf_cookie  # esta tela não tem formulário, e o menu Deletar precisa do cookie
def campaign_home(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    campaign.last_opened_at = timezone.now()
    campaign.save(update_fields=["last_opened_at"])
    types = campaign.recordtype_set.order_by("position").annotate(total=Count("record"))
    return render(request, "campaigns/home.html", {"campaign": campaign, "types": types})


@login_required
@require_POST
def campaign_delete(request, campaign_id):
    get_campaign(request.user, campaign_id).delete()
    return deleted(request, redirect("campaign-list"))


@login_required
def type_new(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    form = RecordTypeForm(campaign, request.POST or None)
    if request.method == "POST" and form.is_valid():
        rtype = create_type(campaign, form.cleaned_data["name"])
        return redirect("record-list", campaign_id=campaign.id, type_id=rtype.id)
    return render(request, "campaigns/type_new.html", {"campaign": campaign, "form": form})


@login_required
@require_POST
def type_delete(request, campaign_id, type_id):
    campaign = get_campaign(request.user, campaign_id)
    get_object_or_404(campaign.recordtype_set, pk=type_id).delete()
    return deleted(request, redirect("campaign-home", campaign_id=campaign.id))
