from django.shortcuts import get_object_or_404

from .models import Campaign


def get_campaign(user, campaign_id):
    return get_object_or_404(Campaign, pk=campaign_id, owner=user)


def get_record(user, record_id):
    from records.models import Record

    return get_object_or_404(Record.objects.select_related("campaign", "record_type"),
                             pk=record_id, campaign__owner=user)


def get_tab(user, tab_id):
    from records.models import Tab

    return get_object_or_404(Tab.objects.select_related("record__campaign", "record__record_type"),
                             pk=tab_id, record__campaign__owner=user)


def get_block(user, block_id):
    from records.models import Block

    return get_object_or_404(Block.objects.select_related("tab__record__campaign", "tab__record__record_type"),
                             pk=block_id, tab__record__campaign__owner=user)
