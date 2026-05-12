from django.urls import path

from . import views

urlpatterns = [
    path('', views.blog_list, name='blog_list'),
    path('create/', views.create_post, name='blog_create'),
    path('<int:post_id>/comment/', views.add_comment, name='blog_add_comment'),
]
