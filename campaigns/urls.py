from django.urls import path

from . import views

urlpatterns = [
    path("", views.root, name="root"),
    path("c/", views.campaign_list, name="campaign-list"),
    path("c/<int:campaign_id>/", views.campaign_home, name="campaign-home"),
    path("c/<int:campaign_id>/tipos/novo/", views.type_new, name="type-new"),
]
