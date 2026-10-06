# Image for the Django + Gunicorn part of Book Tracker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/book_tracker

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY . .

# Copy static files into the shared volume (served by Nginx), then start Gunicorn.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn -c deploy/gunicorn.conf.py book_tracker.wsgi:application"]
