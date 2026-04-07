import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

_csrf_origins_env = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _csrf_origins_env.strip():
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in _csrf_origins_env.split(",") if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host.strip()}"
        for host in ALLOWED_HOSTS
        if host.strip() and host.strip() != "*"
    ]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "library",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bookshelf.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bookshelf.wsgi.application"
ASGI_APPLICATION = "bookshelf.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
ALLOWED_BOOK_EXTENSIONS = {".pdf", ".epub"}
BLOCKED_EXTENSIONS = {".zip"}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

CLAMD_HOST = os.getenv("CLAMD_HOST", "127.0.0.1")
CLAMD_PORT = int(os.getenv("CLAMD_PORT", "3310"))
CLAMD_STRICT = os.getenv("CLAMD_STRICT", "0") == "1"

WORKER_POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "3"))

# ── Email ─────────────────────────────────────────────────────────────────────
# Option A — Resend (recommended, free, no SMTP needed):
#   RESEND_API_KEY=re_xxxxxxxxxxxx
#   EMAIL_FROM=ArenaShelf <onboarding@resend.dev>   # or your verified sender
#
# Option B — SMTP (Gmail, Outlook, etc.):
#   EMAIL_HOST=smtp.gmail.com  EMAIL_PORT=587  EMAIL_USE_TLS=1
#   EMAIL_HOST_USER=you@gmail.com  EMAIL_HOST_PASSWORD=<App Password>
#   EMAIL_FROM=ArenaShelf <you@gmail.com>
#
# If RESEND_API_KEY is set it takes priority over SMTP.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_HOST_USER or "ArenaShelf <onboarding@resend.dev>")
