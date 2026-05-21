from django.conf import settings


class FirebaseConfigError(Exception):
    pass


def _service_account_info() -> dict:
    info = getattr(settings, 'FIREBASE_ADMIN_CONFIG', {}) or {}
    info = {key: value for key, value in info.items() if value}
    if 'private_key' in info:
        info['private_key'] = info['private_key'].replace('\\n', '\n')

    required_keys = [
        'type',
        'project_id',
        'private_key_id',
        'private_key',
        'client_email',
        'client_id',
        'auth_uri',
        'token_uri',
        'auth_provider_x509_cert_url',
        'client_x509_cert_url',
    ]
    if all(info.get(key) for key in required_keys):
        return info
    return {}


def get_firebase_app():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise FirebaseConfigError('firebase-admin is not installed.') from exc

    try:
        return firebase_admin.get_app()
    except ValueError:
        service_account_info = _service_account_info()
        if not service_account_info:
            raise FirebaseConfigError(
                'Firebase admin credentials not found. Set FIREBASE_ADMIN_* in .env.'
            )
        credential = credentials.Certificate(service_account_info)

        options = {}
        database_url = getattr(settings, 'FIREBASE_DATABASE_URL', '')
        if database_url:
            options['databaseURL'] = database_url

        return firebase_admin.initialize_app(credential, options or None)


def verify_firebase_id_token(id_token: str) -> dict:
    try:
        from firebase_admin import auth
    except ImportError as exc:
        raise FirebaseConfigError('firebase-admin is not installed.') from exc

    app = get_firebase_app()
    return auth.verify_id_token(id_token, app=app, clock_skew_seconds=120)

def get_or_create_google_user(email, name='', picture='', email_verified=False):
    try:
        from firebase_admin import auth
    except ImportError as exc:
        raise FirebaseConfigError('firebase-admin is not installed.') from exc

    app = get_firebase_app()
    try:
        return auth.get_user_by_email(email, app=app)
    except auth.UserNotFoundError:
        return auth.create_user(
            email=email,
            email_verified=bool(email_verified),
            display_name=name or None,
            photo_url=picture or None,
            app=app,
        )
