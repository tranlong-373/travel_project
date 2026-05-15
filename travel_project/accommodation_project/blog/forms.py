from django import forms

from .models import BlogComment, BlogPost


class BlogPostForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ['caption']
        widgets = {
            'caption': forms.Textarea(attrs={
                'class': 'blog-textarea',
                'placeholder': 'Bạn muốn chia sẻ điều gì về khách sạn này?',
                'rows': 5,
            }),
        }


class BlogCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ['content']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'blog-comment-input',
                'placeholder': 'Viết bình luận...',
            }),
        }
