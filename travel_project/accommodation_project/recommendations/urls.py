from django.urls import path
from . import views

urlpatterns = [
    path('<int:pref_id>/', views.recommendation_result, name='recommendation_result'),
]