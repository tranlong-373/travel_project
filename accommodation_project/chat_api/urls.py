from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health, name="chat_api_health"),
    path("parse/", views.parse_message, name="chat_api_parse"),
    path("submit/", views.submit_message, name="chat_api_submit"),
]
