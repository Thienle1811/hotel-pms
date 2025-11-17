"""
Django settings for core project.
"""

from pathlib import Path
import os
import dj_database_url # Thư viện hữu ích cho cấu hình database

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# Cấu hình SECRET_KEY an toàn hơn khi triển khai
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-key-for-dev') 

# SECURITY WARNING: don't run with debug turned on in production!
# Tự động chuyển DEBUG = False khi có biến môi trường
DEBUG = os.environ.get('DEBUG', 'True') == 'True'


# CẤU HÌNH ALLOWED_HOSTS
ALLOWED_HOSTS = [
    '127.0.0.1', 
    'localhost', 
    'tên_user_của_bạn.pythonanywhere.com' # Thay thế bằng domain thực tế
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    # Thư viện cho static files
    'django.contrib.staticfiles',
    
    # Ứng dụng quản lý khách sạn của bạn
    'pms', 
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Thêm WhiteNoise ở vị trí này, ngay sau SecurityMiddleware
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# Sử dụng biến môi trường DATABASE_URL nếu có (cho môi trường Production)
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL')
        )
    }
else:
    # Mặc định sử dụng SQLite cho môi trường phát triển cục bộ
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation (Giữ lại cấu hình mặc định)
AUTH_PASSWORD_VALIDATORS = [
   {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
   {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
   {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
   {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'vi' 
TIME_ZONE = 'Asia/Ho_Chi_Minh' 
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
# Thư mục nơi Django sẽ copy tất cả static files cho Production
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Cấu hình WhiteNoise để nén và phục vụ static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# CẤU HÌNH BẢO MẬT BẮT BUỘC CHO PRODUCTION/HTTPS (PythonAnywhere)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True


# CẤU HÌNH CHO HỆ THỐNG ĐĂNG NHẬP
LOGIN_REDIRECT_URL = '/'      
LOGOUT_REDIRECT_URL = '/login/' 
LOGIN_URL = 'login'