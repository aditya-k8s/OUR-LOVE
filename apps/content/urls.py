from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("", views.home, name="home"),
    path("story/", views.story, name="story"),
    path("story/<str:doc_id>/", views.event_detail, name="event_detail"),
    path("memories/", views.memories, name="memories"),
    path("memories/<str:doc_id>/", views.memory_detail, name="memory_detail"),
    path("gallery/", views.gallery, name="gallery"),
    path("moments/", views.moments, name="moments"),
    path("letters/", views.letters, name="letters"),
    path("letters/<str:doc_id>/", views.letter_detail, name="letter_detail"),
    path("words/", views.words, name="words"),
    path("places/", views.places, name="places"),
    path("little-things/", views.gifts, name="gifts"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("future/", views.future, name="future"),
    path("search/", views.search, name="search"),
    path("more/", views.more, name="more"),
]
