# Book Tracker

A small Django application for keeping track of books, built to demonstrate a basic deployment architecture:

```text
Browser
   ↓
Nginx            (port 80, serves /static/, proxies everything else)
   ↓
Gunicorn         (127.0.0.1:8000)
   ↓
Django           (views, forms, templates)
   ↓
MongoDB          (collection: books, accessed with PyMongo)
```

> **Quickest way to run the whole stack:** `docker compose up -d --build`, then open <http://localhost:8082>.
> See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the step-by-step Docker deployment guide.
> The sections below describe a manual install on a Linux server.

## Features

- **Dashboard**: total books, completed books, books currently being read.
- **Books page**: table of all books, change a book's status from a dropdown, edit, delete (with a confirmation page).
- **Add/Edit form**: all fields are required and validated.
- Success and error messages shown after every action.

Each book stored in MongoDB looks like this:

```json
{
  "_id": ObjectId("..."),            // shown in the app as "id"
  "title": "Dune",
  "author": "Frank Herbert",
  "category": "Science Fiction",
  "status": "Reading",               // Want to Read | Reading | Completed
  "created_date": ISODate("2026-10-06T10:00:00Z")
}
```

## Project structure

```text
book_tracker/
├── manage.py
├── requirements.txt
├── .env.example                  # local environment variables
├── book_tracker/                 # Django project
│   ├── settings.py               # reads config from environment variables
│   ├── urls.py
│   └── wsgi.py                   # Gunicorn entry point
├── books/                        # the app
│   ├── db.py                     # all MongoDB access (PyMongo)
│   ├── forms.py
│   ├── views.py
│   ├── urls.py
│   ├── management/commands/
│   │   ├── seed_books.py         # insert sample data
│   │   └── check_mongo.py        # verify the MongoDB connection
│   ├── templates/books/
│   └── static/books/style.css
├── Dockerfile                    # Docker deployment (see DEPLOYMENT.md)
├── docker-compose.yml
└── deploy/
    ├── gunicorn.conf.py
    ├── nginx/book_tracker.conf   # Nginx site for a Linux server
    ├── nginx/docker.conf         # Nginx site for docker compose
    ├── book_tracker.service      # systemd unit
    ├── book_tracker.env.example  # production environment variables (server)
    └── docker.env.example        # environment variables (docker compose)
```

Django's own SQL database is not used (`DATABASES = {}`); everything is stored in MongoDB. Flash messages use cookie storage, so no session table is needed either — there are no migrations to run.

---

## 1. Prerequisites

- Python 3.12
- MongoDB 6.0 or newer (local install, Docker, or a hosted cluster such as MongoDB Atlas)
- For deployment: a Linux server (examples use Ubuntu/Debian) with Nginx

Get the code:

```bash
git clone https://github.com/BRHM1/book-tracker.git book_tracker
cd book_tracker
```

Quick way to get a local MongoDB with Docker: start only the `mongo` service from `docker-compose.yml` (create `deploy/docker.env` first, see [DEPLOYMENT.md](DEPLOYMENT.md#2-configure-environment-variables)). It listens on `127.0.0.1:27017` with the user and password from that file:

```bash
docker compose up -d mongo
```

## 2. Create a virtual environment

```bash
python3.12 -m venv venv

# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` contains Django, PyMongo, Gunicorn and python-dotenv.

## 4. Configure MongoDB

Configuration is read from environment variables. For local development, copy the example file and edit it:

```bash
cp .env.example .env
```

| Variable | Description | Example |
|---|---|---|
| `MONGODB_URI` | MongoDB connection string | `mongodb://username:password@mongodb-server:27017/?authSource=admin` |
| `MONGODB_DATABASE` | Database name | `book_tracker` |
| `DJANGO_SECRET_KEY` | Django secret key | a long random string |
| `DJANGO_DEBUG` | `True` locally, `False` in production | `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names | `example.com,www.example.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins (needed for HTTPS/custom domains) | `https://example.com` |
| `DJANGO_STATIC_ROOT` | Where `collectstatic` puts files (optional) | `/opt/book_tracker/staticfiles` |
| `GUNICORN_BIND` | Gunicorn listen address (optional, default `127.0.0.1:8000`; Docker uses `0.0.0.0:8000`) | `127.0.0.1:8000` |

With the Docker MongoDB from step 1, use `MONGODB_URI=mongodb://USER:PASS@localhost:27017/?authSource=admin` (same user and password as in `deploy/docker.env`).

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Credentials are never hard-coded: `settings.py` only reads `os.environ`. A `.env` file is loaded if present, but real environment variables (e.g. from systemd) take precedence.

## 5. Run Django locally

```bash
python manage.py check_mongo     # confirm MongoDB is reachable
python manage.py seed_books      # add 6 sample books (only if the collection is empty)
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

## 6. Run with Gunicorn

Gunicorn runs on Linux/macOS (not native Windows — use WSL there).

```bash
gunicorn -c deploy/gunicorn.conf.py book_tracker.wsgi:application
```

This binds to `127.0.0.1:8000`. With `DJANGO_DEBUG=False`, Django no longer serves static files — that is Nginx's job (next step). Test that Gunicorn answers:

```bash
curl -I http://127.0.0.1:8000/
```

## 7. Configure Nginx (Linux server)

The examples assume the project lives in `/opt/book_tracker` and runs as a dedicated user `booktracker`.

**a. Install system packages and copy the project**

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nginx

sudo useradd --system --gid www-data --home /opt/book_tracker --shell /usr/sbin/nologin booktracker
sudo mkdir -p /opt/book_tracker
sudo cp -r . /opt/book_tracker/          # or: git clone ... /opt/book_tracker
sudo chown -R booktracker:www-data /opt/book_tracker
```

**b. Create the virtualenv on the server**

```bash
cd /opt/book_tracker
sudo -u booktracker python3.12 -m venv venv
sudo -u booktracker venv/bin/pip install -r requirements.txt
```

**c. Environment variables**

```bash
sudo mkdir -p /etc/book_tracker
sudo cp deploy/book_tracker.env.example /etc/book_tracker/book_tracker.env
sudo nano /etc/book_tracker/book_tracker.env      # set secret key, hosts, MONGODB_URI
sudo chown root:www-data /etc/book_tracker/book_tracker.env
sudo chmod 640 /etc/book_tracker/book_tracker.env
```

**d. Collect static files**

`collectstatic` copies the app's CSS into `STATIC_ROOT` (`/opt/book_tracker/staticfiles`), which Nginx serves at `/static/`:

```bash
sudo -u booktracker bash -c 'set -a; source /etc/book_tracker/book_tracker.env; set +a; venv/bin/python manage.py collectstatic --noinput'
```

**e. Enable the Nginx site**

Edit `server_name` in `deploy/nginx/book_tracker.conf`, then:

```bash
sudo cp deploy/nginx/book_tracker.conf /etc/nginx/sites-available/book_tracker
sudo ln -s /etc/nginx/sites-available/book_tracker /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default     # optional: disable the default site
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Create the systemd service

```bash
sudo cp deploy/book_tracker.service /etc/systemd/system/book_tracker.service
sudo systemctl daemon-reload
sudo systemctl enable --now book_tracker
sudo systemctl status book_tracker
```

### Starting / stopping / restarting

| Task | Command |
|---|---|
| Start | `sudo systemctl start book_tracker` |
| Stop | `sudo systemctl stop book_tracker` |
| Restart (after code or env changes) | `sudo systemctl restart book_tracker` |
| Graceful reload of workers | `sudo systemctl reload book_tracker` |
| View logs | `sudo journalctl -u book_tracker -f` |
| Reload Nginx after config changes | `sudo nginx -t && sudo systemctl reload nginx` |

**Deploying a new version:**

```bash
cd /opt/book_tracker
sudo -u booktracker git pull                         # or copy the new files
sudo -u booktracker venv/bin/pip install -r requirements.txt
sudo -u booktracker bash -c 'set -a; source /etc/book_tracker/book_tracker.env; set +a; venv/bin/python manage.py collectstatic --noinput'
sudo systemctl restart book_tracker
```

## 9. Verify Django can connect to MongoDB

Locally:

```bash
python manage.py check_mongo
```

On the server (using the production environment file):

```bash
cd /opt/book_tracker
sudo -u booktracker bash -c 'set -a; source /etc/book_tracker/book_tracker.env; set +a; venv/bin/python manage.py check_mongo'
```

Expected output:

```text
Connected to MongoDB.
  Server version : 7.0.x
  Database       : book_tracker
  Books stored   : 6
```

Load the sample data on the server the same way, replacing `check_mongo` with `seed_books`.

Then check the full chain through Nginx:

```bash
curl -I http://your-server/            # should return 200 OK
curl -I http://your-server/static/books/style.css   # served by Nginx
```

If the dashboard shows *"Could not reach MongoDB"*, check `MONGODB_URI`, that MongoDB is running, and that its port (27017) is reachable from the server. Logs: `journalctl -u book_tracker`.
