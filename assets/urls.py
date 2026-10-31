from django.urls import path

from . import views

urlpatterns = [
    path("r/<int:record_id>/arquivos/", views.asset_upload, name="asset-upload"),
    path("arquivos/<uuid:asset_id>/", views.asset_open, name="asset-open"),
    path("arquivos/<uuid:asset_id>/arquivo/", views.asset_file, name="asset-file"),
    path("arquivos/<uuid:asset_id>/principal/", views.asset_main, name="asset-main"),
    path("arquivos/<uuid:asset_id>/excluir/", views.asset_delete, name="asset-delete"),
]
