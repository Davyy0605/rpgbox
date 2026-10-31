from django.urls import path

from . import template_views as tv
from . import views

urlpatterns = [
    path("", views.root, name="root"),
    path("c/", views.campaign_list, name="campaign-list"),
    path("c/<int:campaign_id>/", views.campaign_home, name="campaign-home"),
    path("c/<int:campaign_id>/tipos/novo/", views.type_new, name="type-new"),
    path("c/<int:campaign_id>/t/<int:type_id>/modelo/", tv.template_edit, name="template-edit"),
    path("modelo/tipo/<int:type_id>/campo/", tv.field_add, name="field-add"),
    path("modelo/campo/<int:field_id>/renomear/", tv.field_rename, name="field-rename"),
    path("modelo/campo/<int:field_id>/mover/", tv.field_move, name="field-move"),
    path("modelo/campo/<int:field_id>/remover/", tv.field_remove, name="field-remove"),
    path("modelo/tipo/<int:type_id>/aba/", tv.tabdef_add, name="tabdef-add"),
    path("modelo/aba/<int:tabdef_id>/renomear/", tv.tabdef_rename, name="tabdef-rename"),
    path("modelo/aba/<int:tabdef_id>/mover/", tv.tabdef_move, name="tabdef-move"),
    path("modelo/aba/<int:tabdef_id>/remover/", tv.tabdef_remove, name="tabdef-remove"),
    path("modelo/grupo/<int:group_id>/renomear/", tv.group_rename, name="group-rename"),
    path("modelo/grupo/<int:group_id>/remover/", tv.group_remove, name="group-remove"),
]
