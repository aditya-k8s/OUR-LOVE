from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("settings/", views.settings_view, name="settings"),
    path("export/", views.export_view, name="export"),
    path("demo/clear/", views.clear_demo_view, name="clear_demo"),
    path("upload/<str:kind>/", views.upload_view, name="upload"),
    path("<str:key>/", views.list_view, name="list"),
    path("<str:key>/new/", views.edit_view, name="create"),
    path("<str:key>/<str:doc_id>/edit/", views.edit_view, name="edit"),
    path("<str:key>/<str:doc_id>/delete/", views.delete_view, name="delete"),
    path("<str:key>/<str:doc_id>/toggle/<str:field>/", views.toggle_view, name="toggle"),
    path("<str:key>/<str:doc_id>/move/<str:direction>/", views.reorder_view, name="reorder"),
]
