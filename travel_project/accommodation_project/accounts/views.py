import json
import logging
import re
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token

from .forms import RegisterForm
from .firebase_service import (
    FirebaseConfigError,
    get_or_create_google_user,
    verify_firebase_id_token,
)
from .models import Profile, Favorite
from accommodations.models import Accommodation


logger = logging.getLogger(__name__)
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_STATE_SALT = 'accounts.google_oauth_state'
GOOGLE_STATE_MAX_AGE = 300


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )

            Profile.objects.create(user=user)

            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {
        'form': form,
        'firebase_config': settings.FIREBASE_WEB_CONFIG,
        'google_login_url': settings.GOOGLE_URL or '/auth/google/start',
    })


def google_start(request):
    missing = _missing_google_settings()
    if missing:
        messages.error(request, f"Google login thiếu cấu hình: {', '.join(missing)}")
        return redirect('login')

    state = signing.dumps(
        {'next': _safe_next_url(request, request.GET.get('next') or '/')},
        salt=GOOGLE_STATE_SALT,
    )

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(f'{GOOGLE_AUTH_URL}?{urlencode(params)}')


def google_callback(request):
    state = request.GET.get('state', '')
    code = request.GET.get('code', '')
    error = request.GET.get('error', '')

    if error:
        messages.error(request, f'Google login failed: {error}')
        return redirect('login')

    try:
        state_data = signing.loads(
            state,
            salt=GOOGLE_STATE_SALT,
            max_age=GOOGLE_STATE_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        messages.error(request, 'Google login không hợp lệ hoặc đã hết hạn.')
        return redirect('login')

    next_url = _safe_next_url(request, state_data.get('next') or '/')
    if not code:
        messages.error(request, 'Google không trả về authorization code.')
        return redirect('login')

    try:
        token_response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': settings.GOOGLE_REDIRECT_URI,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        )
        token_response.raise_for_status()
        google_token = token_response.json().get('id_token')
        if not google_token:
            messages.error(request, 'Google không trả về id_token.')
            return redirect('login')

        profile = google_id_token.verify_oauth2_token(
            google_token,
            GoogleRequest(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
        email = (profile.get('email') or '').strip().lower()
        name = (profile.get('name') or '').strip()
        picture = (profile.get('picture') or '').strip()
        if not email:
            messages.error(request, 'Google token không có email.')
            return redirect('login')

        firebase_user = get_or_create_google_user(
            email=email,
            name=name,
            picture=picture,
            email_verified=profile.get('email_verified'),
        )
        user, _ = _sync_sql_user(
            firebase_uid=firebase_user.uid,
            email=email,
            name=name,
            picture=picture,
        )
        _login_sql_user(request, user)
        return redirect(next_url)
    except requests.HTTPError:
        logger.exception('Google token exchange failed')
        messages.error(request, 'Không đổi được Google code lấy token.')
    except FirebaseConfigError as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception('Google login failed')
        messages.error(request, 'Google login thất bại. Kiểm tra Google OAuth và Firebase Admin.')

    return redirect('login')


@csrf_exempt
def firebase_login(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)

    body, error_response = _read_firebase_login_body(request)
    wants_redirect = _wants_redirect(body)
    if error_response:
        return redirect('login') if wants_redirect else error_response

    id_token = (body.get('idToken') or '').strip()
    if not id_token:
        return _firebase_login_error('Field idToken is required', 400, wants_redirect)

    try:
        decoded = verify_firebase_id_token(id_token)
    except FirebaseConfigError as exc:
        return _firebase_login_error(str(exc), 500, wants_redirect)
    except Exception:
        return _firebase_login_error('Invalid Firebase token', 401, wants_redirect)

    firebase_uid = decoded.get('uid')
    email = (decoded.get('email') or '').strip().lower()
    name = (decoded.get('name') or '').strip()
    picture = (decoded.get('picture') or '').strip()

    if not email:
        return _firebase_login_error('Firebase token does not include an email', 400, wants_redirect)

    user, profile = _sync_sql_user(
        firebase_uid=firebase_uid,
        email=email,
        name=name,
        picture=picture,
    )
    _login_sql_user(request, user)

    if wants_redirect:
        return redirect(_safe_next_url(request, body.get('next') or '/'))

    display_name = user.get_full_name() or profile.full_name or user.username
    return JsonResponse(
        {
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': display_name,
                'firebase_uid': profile.firebase_uid,
                'avatar_url': profile.avatar_url,
            },
        },
        status=200,
    )


def _missing_google_settings():
    required = {
        'GOOGLE_CLIENT_ID': settings.GOOGLE_CLIENT_ID,
        'GOOGLE_CLIENT_SECRET': settings.GOOGLE_CLIENT_SECRET,
        'GOOGLE_REDIRECT_URI': settings.GOOGLE_REDIRECT_URI,
    }
    return [key for key, value in required.items() if not value]


def _sync_sql_user(firebase_uid, email, name='', picture=''):
    profile_by_uid = None
    if firebase_uid:
        profile_by_uid = Profile.objects.select_related('user').filter(firebase_uid=firebase_uid).first()

    user = profile_by_uid.user if profile_by_uid else User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User(username=_unique_username(email, firebase_uid), email=email)
        first_name, last_name = _split_name(name)
        user.first_name = first_name
        user.last_name = last_name
        user.set_unusable_password()
        user.save()
    else:
        first_name, last_name = _split_name(name)
        update_fields = []
        if first_name and not user.first_name:
            user.first_name = first_name
            update_fields.append('first_name')
        if last_name and not user.last_name:
            user.last_name = last_name
            update_fields.append('last_name')
        if update_fields:
            user.save(update_fields=update_fields)

    profile, _ = Profile.objects.get_or_create(user=user)
    profile_fields = []
    if name and not profile.full_name:
        profile.full_name = name
        profile_fields.append('full_name')
    if firebase_uid and profile.firebase_uid != firebase_uid:
        profile.firebase_uid = firebase_uid
        profile_fields.append('firebase_uid')
    if picture and profile.avatar_url != picture:
        profile.avatar_url = picture
        profile_fields.append('avatar_url')
    if profile_fields:
        profile.save(update_fields=profile_fields)

    return user, profile


def _login_sql_user(request, user):
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.save()


def _read_firebase_login_body(request):
    content_type = request.META.get('CONTENT_TYPE', '')
    if content_type.startswith('application/json'):
        return _read_json_body(request)

    return request.POST, None


def _wants_redirect(body):
    if not body:
        return False
    value = body.get('redirect') or body.get('_redirect') or ''
    return str(value).lower() in {'1', 'true', 'yes'}


def _safe_next_url(request, next_url):
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return '/'


def _firebase_login_error(message, status, wants_redirect=False):
    if wants_redirect:
        return redirect('login')
    return JsonResponse({'success': False, 'error': message}, status=status)


def _read_json_body(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return None, JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    if not isinstance(body, dict):
        return None, JsonResponse({'success': False, 'error': 'JSON body must be an object'}, status=400)

    return body, None


def _unique_username(email, firebase_uid):
    base = re.sub(r'[^A-Za-z0-9_@.+-]', '_', email or firebase_uid or 'firebase_user')
    base = base[:140].strip('_') or 'firebase_user'
    candidate = base
    counter = 1

    while User.objects.filter(username=candidate).exists():
        suffix = f'_{counter}'
        candidate = f'{base[:150 - len(suffix)]}{suffix}'
        counter += 1

    return candidate


def _split_name(name):
    parts = (name or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    favorites = Favorite.objects.filter(user=request.user).select_related('accommodation')

    if request.method == 'POST':
        profile.full_name = request.POST.get('full_name', '')
        profile.phone = request.POST.get('phone', '')
        profile.address = request.POST.get('address', '')
        profile.save()
        return redirect('profile')

    return render(request, 'accounts/profile.html', {
        'profile': profile,
        'favorites': favorites
    })


@login_required
def add_favorite(request, accommodation_id):
    if request.method == 'POST':
        accommodation = get_object_or_404(Accommodation, id=accommodation_id)
        Favorite.objects.get_or_create(user=request.user, accommodation=accommodation)
    return redirect('accommodation_detail', pk=accommodation_id)


@login_required
def remove_favorite(request, accommodation_id):
    if request.method == 'POST':
        accommodation = get_object_or_404(Accommodation, id=accommodation_id)
        Favorite.objects.filter(user=request.user, accommodation=accommodation).delete()
    return redirect('accommodation_detail', pk=accommodation_id)
