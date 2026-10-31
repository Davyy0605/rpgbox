from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def health(request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health, name="health"),
    path("", include("accounts.urls")),
]
