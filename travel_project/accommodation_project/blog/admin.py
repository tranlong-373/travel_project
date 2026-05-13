from django.contrib import admin
from django.utils.html import format_html

from .models import BlogComment, BlogImage, BlogPost


class BlogImageInline(admin.TabularInline):
    model = BlogImage
    extra = 0
    fields = ('image_preview', 'image', 'uploaded_at')
    readonly_fields = ('image_preview', 'uploaded_at')

    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="width:86px;height:58px;object-fit:cover;border-radius:6px;" />',
                obj.image.url,
            )
        return 'No image'

    image_preview.short_description = 'Preview'


class BlogCommentInline(admin.TabularInline):
    model = BlogComment
    extra = 0
    fields = ('author', 'content', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('first_image_preview', 'author', 'accommodation', 'short_caption', 'image_count', 'comment_count', 'created_at')
    list_filter = ('created_at', 'accommodation__area', 'accommodation')
    search_fields = ('caption', 'author__username', 'author__email', 'accommodation__name')
    autocomplete_fields = ('author', 'accommodation')
    list_select_related = ('author', 'accommodation')
    inlines = [BlogImageInline, BlogCommentInline]

    def short_caption(self, obj):
        return obj.caption[:90] + ('...' if len(obj.caption) > 90 else '')

    short_caption.short_description = 'Caption'

    def image_count(self, obj):
        return obj.images.count()

    image_count.short_description = 'Images'

    def comment_count(self, obj):
        return obj.comments.count()

    comment_count.short_description = 'Comments'

    def first_image_preview(self, obj):
        image = obj.images.first()
        if image:
            return format_html(
                '<img src="{}" style="width:64px;height:44px;object-fit:cover;border-radius:6px;" />',
                image.image.url,
            )
        return format_html('<span style="color:#94a3b8;">No image</span>')

    first_image_preview.short_description = 'Image'

