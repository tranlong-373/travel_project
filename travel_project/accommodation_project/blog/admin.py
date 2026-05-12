from django.contrib import admin

from .models import BlogComment, BlogImage, BlogPost


class BlogImageInline(admin.TabularInline):
    model = BlogImage
    extra = 0


class BlogCommentInline(admin.TabularInline):
    model = BlogComment
    extra = 0
    readonly_fields = ['author', 'created_at']


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ['author', 'accommodation', 'created_at']
    list_filter = ['created_at', 'accommodation']
    search_fields = ['caption', 'author__username', 'accommodation__name']
    inlines = [BlogImageInline, BlogCommentInline]


@admin.register(BlogImage)
class BlogImageAdmin(admin.ModelAdmin):
    list_display = ['post', 'uploaded_at']


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'post', 'created_at']
    search_fields = ['content', 'author__username']
