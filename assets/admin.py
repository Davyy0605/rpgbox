from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("filename", "owner", "kind", "size", "created_at")
    readonly_fields = ("owner", "record", "tab", "key", "thumb_key")
