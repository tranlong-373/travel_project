from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Profile
    path('profile/', views.profile_view, name='profile'),

    # Favorite
    path('favorite/add/<int:accommodation_id>/', views.add_favorite, name='add_favorite'),
    path('favorite/remove/<int:accommodation_id>/', views.remove_favorite, name='remove_favorite'),
]