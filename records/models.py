from django.db import models


class Record(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE)
    record_type = models.ForeignKey("campaigns.RecordType", on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    fields = models.JSONField(default=dict, blank=True)
    group = models.ForeignKey("campaigns.ListGroup", null=True, blank=True, on_delete=models.SET_NULL)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Tab(models.Model):
    record = models.ForeignKey(Record, on_delete=models.CASCADE)
    tab_def = models.ForeignKey("campaigns.TabDef", null=True, blank=True, on_delete=models.SET_NULL)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="subtabs")
    title = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title


class Block(models.Model):
    KINDS = [("text", "text"), ("embed", "embed")]
    tab = models.ForeignKey(Tab, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KINDS)
    position = models.PositiveIntegerField(default=0)
    content = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    embed_record = models.ForeignKey(Record, null=True, blank=True, on_delete=models.SET_NULL, related_name="embedded_in")
    embed_anchor = models.CharField(max_length=80, blank=True)
    embed_label = models.CharField(max_length=160, blank=True)
