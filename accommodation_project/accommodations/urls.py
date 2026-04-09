from django.urls import path
from . import views

urlpatterns = [
    path('', views.accommodation_list, name='accommodation_list'),
    path('<int:pk>/', views.accommodation_detail, name='accommodation_detail'),
]