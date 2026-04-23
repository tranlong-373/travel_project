from django.urls import path

from . import views

urlpatterns = [
    path("parse/", views.parse_voice, name="voice_api_parse"),
]
