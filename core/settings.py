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
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    # Thư viện cho static files
    'django.contrib.staticfiles',
    
    # Thư viện hỗ trợ định dạng số tiền (intcomma)
    'django.contrib.humanize',

    # Ứng dụng quản lý khách sạn của bạn
    'pms',
    'rest_framework',
    'rest_framework.authtoken',
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
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'vi'

TIME_ZONE = 'Asia/Ho_Chi_Minh'

USE_I18N = True

USE_TZ = True


# ==============================================================
# CẤU HÌNH ĐỊNH DẠNG NGÀY GIỜ (24H) & SỐ HỌC
# ==============================================================

# 1. Tắt USE_L10N để Django không tự động format theo vùng miền mặc định
# (Giúp ép buộc sử dụng các format mình định nghĩa bên dưới)
USE_L10N = False 

# 2. Định dạng hiển thị trên Web (Template)
# 'H' là giờ 24h (00-23), 'h' là giờ 12h (01-12), 'A' là AM/PM
DATE_FORMAT = 'd/m/Y'           # Ví dụ: 25/11/2023
DATETIME_FORMAT = 'd/m/Y H:i'   # Ví dụ: 25/11/2023 14:30
TIME_FORMAT = 'H:i'             # Ví dụ: 14:30

# 3. Định dạng nhập liệu (Forms) - Để bạn nhập tay được
DATE_INPUT_FORMATS = ['%d/%m/%Y', '%Y-%m-%d']
DATETIME_INPUT_FORMATS = [
    '%d/%m/%Y %H:%M',       # Ưu tiên dạng ngày/tháng/năm giờ:phút
    '%d/%m/%Y %H:%M:%S',
    '%Y-%m-%d %H:%M',       # Hỗ trợ thêm dạng năm-tháng-ngày (chuẩn input HTML5)
    '%Y-%m-%d %H:%M:%S',
]
TIME_INPUT_FORMATS = ['%H:%M', '%H:%M:%S']

# 4. Định dạng số tiền (Dấu phẩy ngăn cách hàng nghìn)
# (Giữ lại cấu hình này để số tiền hiển thị đẹp: 1,000,000)
USE_THOUSAND_SEPARATOR = True
THOUSAND_SEPARATOR = ','
DECIMAL_SEPARATOR = '.'
NUMBER_GROUPING = 3


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

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')