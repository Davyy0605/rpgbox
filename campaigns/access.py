from django.shortcuts import get_object_or_404

from .models import Campaign


def get_campaign(user, campaign_id):
    return get_object_or_404(Campaign, pk=campaign_id, owner=user)
