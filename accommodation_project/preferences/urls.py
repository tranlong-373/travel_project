from django.urls import path
from . import views

urlpatterns = [
    path('', views.preference_form_view, name='preference_form'),
]