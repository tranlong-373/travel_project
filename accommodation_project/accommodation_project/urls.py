from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home(request):
    return render(request, 'home.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('accounts.urls')),
    path('accommodations/', include('accommodations.urls')),
    path('preferences/', include('preferences.urls')),
    path('recommendations/', include('recommendations.urls')),
     path("chat-api/", include("chat_api.urls")),
]