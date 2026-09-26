from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("<str:slug>/", views.CollectionView.as_view(), name="collection"),
    path("<str:slug>/<str:doc_id>/", views.DocumentView.as_view(), name="document"),
]
