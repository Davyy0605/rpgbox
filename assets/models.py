import uuid

from django.conf import settings
from django.db import models


class Asset(models.Model):
    KINDS = [("image", "image"), ("pdf", "pdf"), ("file", "file")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    record = models.ForeignKey("records.Record", on_delete=models.CASCADE)
    tab = models.ForeignKey("records.Tab", null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=10, choices=KINDS)
    filename = models.CharField(max_length=255)
    key = models.CharField(max_length=300)
    thumb_key = models.CharField(max_length=300, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename


from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=Asset)
def remove_files(sender, instance, **kwargs):
    from django.core.files.storage import default_storage

    for key in (instance.key, instance.thumb_key):
        if key:
            default_storage.delete(key)
