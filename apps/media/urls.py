from django.urls import path

from . import views

app_name = "media"

urlpatterns = [
    path("<path:key>", views.serve, name="serve"),
]
