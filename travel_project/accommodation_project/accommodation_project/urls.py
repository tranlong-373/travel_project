from django.contrib import admin
from django.urls import path, include

from accommodations.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('accounts/', include('accounts.urls')),
    path('accommodations/', include('accommodations.urls')),
    path('preferences/', include('preferences.urls')),
    path('recommendations/', include('recommendations.urls')),
    path('chat_api/', include('chat_api.urls')),
]
