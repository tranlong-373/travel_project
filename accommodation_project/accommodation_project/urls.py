from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from accommodations.models import Accommodation   # ← thêm dòng này

def home(request):
    accommodations = Accommodation.objects.all()[:8]   # ← thêm dòng này
    return render(request, 'home.html', {'accommodations': accommodations})  # ← truyền data vào

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('accounts.urls')),
    path('accommodations/', include('accommodations.urls')),
    path('preferences/', include('preferences.urls')),
    path('recommendations/', include('recommendations.urls')),
    path('api/chat/', include('chat_api.urls')),
    path('chat_api/', include('chat_api.urls')),
    
]