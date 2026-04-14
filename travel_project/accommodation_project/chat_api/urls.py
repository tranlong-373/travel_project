from django.urls import path
from . import views

urlpatterns = [
    path("", views.parse_message, name="chat_api_parse"),      # mặc định parse
    path("submit/", views.submit_message, name="chat_api_submit"),
    path("health/", views.health, name="chat_api_health"),
]