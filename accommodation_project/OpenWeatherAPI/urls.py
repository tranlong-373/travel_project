from django.urls import path

from OpenWeatherAPI import views

urlpatterns = [
    path("weather/", views.current_weather, name="openweather-current"),
]
