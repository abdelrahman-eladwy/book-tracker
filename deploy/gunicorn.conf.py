"""
Gunicorn configuration for Book Tracker.

Usage (from the project folder, with the virtualenv active):

    gunicorn -c deploy/gunicorn.conf.py book_tracker.wsgi:application
"""
import multiprocessing
import os

# Only listen on localhost: Nginx is the only thing that talks to Gunicorn.
# (Docker overrides this with GUNICORN_BIND=0.0.0.0:8000 so the Nginx
# container can reach it over the internal Docker network.)
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# A common starting point is (2 x CPU cores) + 1, capped to keep it small.
workers = min(multiprocessing.cpu_count() * 2 + 1, 5)

timeout = 30
graceful_timeout = 30

# Log to stdout/stderr; under systemd this ends up in `journalctl -u book_tracker`.
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Trust X-Forwarded-* headers coming from Nginx on the same machine.
forwarded_allow_ips = "127.0.0.1"
