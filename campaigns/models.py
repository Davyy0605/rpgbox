import uuid

from django.conf import settings
from django.db import models


class Campaign(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    last_opened_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class RecordType(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "name"], name="uniq_type_name_per_campaign")]

    def __str__(self):
        return self.name


def new_key():
    return str(uuid.uuid4())


class FieldDef(models.Model):
    KINDS = [("short", "short"), ("long", "long"), ("number", "number"), ("link", "link")]
    record_type = models.ForeignKey(RecordType, on_delete=models.CASCADE)
    key = models.CharField(max_length=36, default=new_key)
    label = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=KINDS)
    position = models.PositiveIntegerField(default=0)
    removed = models.BooleanField(default=False)


class TabDef(models.Model):
    record_type = models.ForeignKey(RecordType, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)
    removed = models.BooleanField(default=False)


class ListGroup(models.Model):
    record_type = models.ForeignKey(RecordType, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)
