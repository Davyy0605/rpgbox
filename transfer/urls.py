from django.urls import path

from . import views

urlpatterns = [
    path("r/<int:record_id>/copiar/", views.record_copy, name="record-copy"),
    path("c/<int:campaign_id>/t/<int:type_id>/trilhas/", views.tracks_bulk, name="tracks-bulk"),
]
