from django.urls import path
from . import views

urlpatterns = [
    path('', views.accommodation_list, name='accommodation_list'),
    path('collaborate/', views.partner_register, name='partner_register'),
    path('review/<int:accommodation_id>/', views.add_review, name='add_review'),
    path('<int:pk>/', views.accommodation_detail, name='accommodation_detail'),
]