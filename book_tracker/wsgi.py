"""
WSGI entry point used by Gunicorn:

    gunicorn book_tracker.wsgi:application
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "book_tracker.settings")

application = get_wsgi_application()
