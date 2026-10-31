from django.shortcuts import get_object_or_404

from .models import Campaign


def get_campaign(user, campaign_id):
    return get_object_or_404(Campaign, pk=campaign_id, owner=user)


def get_record(user, record_id):
    from records.models import Record

    return get_object_or_404(Record.objects.select_related("campaign", "record_type"),
                             pk=record_id, campaign__owner=user)
