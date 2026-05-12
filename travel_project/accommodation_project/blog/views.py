from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accommodations.models import Accommodation

from .forms import BlogCommentForm, BlogPostForm
from .models import BlogComment, BlogImage, BlogPost


def blog_list(request):
    posts = (
        BlogPost.objects.select_related('author', 'accommodation')
        .prefetch_related('images', 'comments__author')
        .all()
    )
    selected_accommodation = None
    accommodation_id = request.GET.get('accommodation')

    if accommodation_id:
        selected_accommodation = get_object_or_404(Accommodation, id=accommodation_id)
        posts = posts.filter(accommodation=selected_accommodation)

    paginator = Paginator(posts, 8)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    query_params = request.GET.copy()
    query_params.pop('page', None)

    return render(request, 'blog/blog_list.html', {
        'page_obj': page_obj,
        'comment_form': BlogCommentForm(),
        'selected_accommodation': selected_accommodation,
        'query_string': query_params.urlencode(),
    })


@login_required
def create_post(request):
    search_query = request.GET.get('q', '').strip()
    accommodation_results = Accommodation.objects.none()

    if search_query:
        accommodation_results = Accommodation.objects.filter(
            Q(name__icontains=search_query)
            | Q(area__icontains=search_query)
            | Q(address__icontains=search_query)
        ).order_by('name')[:10]

    if request.method == 'POST':
        form = BlogPostForm(request.POST)
        accommodation_id = request.POST.get('accommodation')
        accommodation = None

        if accommodation_id:
            accommodation = get_object_or_404(Accommodation, id=accommodation_id)

        if form.is_valid() and accommodation:
            post = form.save(commit=False)
            post.author = request.user
            post.accommodation = accommodation
            post.save()

            for image in request.FILES.getlist('images'):
                BlogImage.objects.create(post=post, image=image)

            messages.success(request, 'Đã đăng bài chia sẻ của bạn.')
            return redirect('blog_list')

        if not accommodation:
            messages.error(request, 'Vui lòng tìm và chọn khách sạn muốn liên kết.')
    else:
        form = BlogPostForm()

    return render(request, 'blog/blog_form.html', {
        'form': form,
        'search_query': search_query,
        'accommodation_results': accommodation_results,
    })


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(BlogPost, id=post_id)

    if request.method == 'POST':
        form = BlogCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()

    return redirect('blog_list')
