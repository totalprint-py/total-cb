"""URL configuration for totalcb project.

El URLconf raíz delega en ``conciliacion.urls`` (Fase 6 — GREEN).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("conciliacion.urls")),
]
