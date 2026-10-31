from django.urls import path

from . import views

urlpatterns = [
    path("c/<int:campaign_id>/t/<int:type_id>/", views.record_list, name="record-list"),
    path("c/<int:campaign_id>/t/<int:type_id>/novo/", views.record_new, name="record-new"),
    path("c/<int:campaign_id>/t/<int:type_id>/grupos/novo/", views.group_add, name="group-add"),
    path("r/<int:record_id>/", views.record_detail, name="record-detail"),
    path("r/<int:record_id>/painel/", views.record_panel, name="record-panel"),
    path("r/<int:record_id>/grupo/", views.record_group, name="record-group"),
    path("r/<int:record_id>/abas/nova/", views.tab_add, name="tab-add"),
    path("r/<int:record_id>/abas/<int:tab_id>/sub/", views.subtab_add, name="subtab-add"),
    path("abas/<int:tab_id>/apagar/", views.tab_delete, name="tab-delete"),
    path("abas/<int:tab_id>/blocos/", views.block_add, name="block-add"),
    path("abas/<int:tab_id>/incorporar/", views.embed_add, name="embed-add"),
    path("blocos/<int:block_id>/", views.block_save, name="block-save"),
    path("blocos/<int:block_id>/apagar/", views.block_delete, name="block-delete"),
    path("r/<int:record_id>/campos/", views.field_save, name="field-save"),
    path("r/<int:record_id>/renomear/", views.record_rename, name="record-rename"),
    path("r/<int:record_id>/apagar/", views.record_delete, name="record-delete"),
]
