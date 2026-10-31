from django.db import models


class Link(models.Model):
    KINDS = [("mention", "mention"), ("embed", "embed")]
    source_record = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="links_out")
    target_record = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="links_in")
    target_anchor = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=10, choices=KINDS)


class SearchEntry(models.Model):
    KINDS = [("record", "record"), ("heading", "heading"), ("text", "text")]
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE)
    record = models.ForeignKey("records.Record", on_delete=models.CASCADE)
    anchor = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=300)
    title_norm = models.CharField(max_length=300)
    body_norm = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=KINDS)

    class Meta:
        indexes = [models.Index(fields=["campaign"])]
