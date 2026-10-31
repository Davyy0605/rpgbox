from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Sum

from assets.models import Asset

from .models import User


def _mb(n):
    return f"{n / (1024 * 1024):.1f} MB"


@admin.register(User)
class RpgUserAdmin(UserAdmin):
    list_display = (*UserAdmin.list_display, "storage")

    @admin.display(description="Espaço usado")
    def storage(self, user):
        return _mb(Asset.objects.filter(owner=user).aggregate(t=Sum("size"))["t"] or 0)

    def changelist_view(self, request, extra_context=None):
        total = Asset.objects.aggregate(t=Sum("size"))["t"] or 0
        return super().changelist_view(request, {**(extra_context or {}), "title": f"Usuários (total: {_mb(total)})"})
