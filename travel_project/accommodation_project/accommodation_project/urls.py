from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from accounts.views import firebase_login, google_callback, google_start
from accommodations.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('api/auth/firebase-login/', firebase_login, name='api_firebase_login'),
    path('auth/google/start', google_start, name='google_start'),
    path('auth/google/callback', google_callback, name='google_callback'),
    path('accounts/', include('accounts.urls')),
    path('accommodations/', include('accommodations.urls')),
    path('preferences/', include('preferences.urls')),
    path('recommendations/', include('recommendations.urls')),
    path('chat_api/', include('chat_api.urls')),
    path('api/chat/', include('chat_api.urls')),
    path('api/voice/', include('voice_api.urls')),
    path('blog/', include('blog.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
