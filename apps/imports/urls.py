from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.index, name="index"),
    path("jobs/<str:job_id>/", views.job_detail, name="job"),
    path("jobs/<str:job_id>/bulk/", views.bulk, name="bulk"),
    path("review/<str:pending_id>/", views.review, name="review"),
]
