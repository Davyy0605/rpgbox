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
]
