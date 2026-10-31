from django.urls import path

from . import views

urlpatterns = [
    path("c/<int:campaign_id>/busca/", views.search, name="search"),
    path("c/<int:campaign_id>/sugestoes/", views.suggest, name="suggest"),
]
