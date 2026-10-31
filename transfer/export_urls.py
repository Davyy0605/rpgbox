from django.urls import path

from . import export_views

urlpatterns = [
    path("c/<int:campaign_id>/exportar/", export_views.campaign_export, name="campaign-export"),
]
