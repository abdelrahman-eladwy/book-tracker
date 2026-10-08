# Book Tracker: Deployment Guide (Docker)

This guide deploys the full stack with Docker Compose on any machine that has Docker (Windows, macOS or Linux):

```text
Browser ──► Nginx :8082 ──► Gunicorn app:8000 ──► Django ──► MongoDB mongo:27017
            (container)       (container)                      (container)
```

| Container | Image | Role | Exposed to the host |
|---|---|---|---|
| `book-tracker-nginx` | `nginx:stable` | Serves `/static/`, proxies everything else to Gunicorn | `http://localhost:8082` |
| `book-tracker-app` | built from `Dockerfile` (Python 3.12) | Runs `collectstatic`, then Gunicorn + Django | no (internal only) |
| `book-tracker-mongo` | `mongo:7` | Stores the `books` collection | `127.0.0.1:27017` (local machine only) |

All three use `restart: unless-stopped`, so they start again automatically when Docker starts (for example after a reboot) unless you stopped them yourself.

> To deploy on a plain Linux server **without Docker** (Nginx + Gunicorn + systemd installed directly), follow sections 7–8 of [README.md](README.md) instead.

---

## Files involved

```text
book_tracker/
├── Dockerfile                    # image for Django + Gunicorn
├── docker-compose.yml            # mongo + app + nginx
├── .dockerignore
└── deploy/
    ├── docker.env.example        # template for environment variables
    ├── docker.env                # your real values (git-ignored, create it in step 2)
    ├── gunicorn.conf.py          # Gunicorn settings (bind address from GUNICORN_BIND)
    └── nginx/docker.conf         # Nginx site used by the nginx container
```

---

## 1. Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- Check that it works:

  ```bash
  docker version
  docker compose version
  ```

- Port **8082** must be free (8080 is used by Jenkins, 8081 by the Jenkins pipeline deploy). To use another port (e.g. 9090), change `"0.0.0.0:8082:80"` to `"0.0.0.0:9090:80"` in `docker-compose.yml` and use that port in `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Git, to get the code:

  ```bash
  git clone https://github.com/BRHM1/book-tracker.git book_tracker
  cd book_tracker
  ```

## 2. Configure environment variables

All commands below are run from the `book_tracker/` folder (the one containing `docker-compose.yml`).

```bash
cp deploy/docker.env.example deploy/docker.env      # Windows PowerShell: copy deploy\docker.env.example deploy\docker.env
```

Edit `deploy/docker.env`:

| Variable | What to set |
|---|---|
| `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD` | MongoDB admin user. **Only applied the first time** the data volume is created. |
| `MONGODB_URI` | Same user and password, host `mongo`: `mongodb://USER:PASS@mongo:27017/?authSource=admin` |
| `MONGODB_DATABASE` | `book_tracker` |
| `DJANGO_SECRET_KEY` | A long random string: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | Host names used in the browser, e.g. `localhost,127.0.0.1` (add your server IP or domain) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Full origins incl. port, e.g. `http://localhost:8082` (add `http://your-server-ip:8082`) |

Don't put quotes around values. If the password contains `@ : / ? #`, URL-encode it in `MONGODB_URI`.

## 3. Build and start

```bash
docker compose up -d --build
```

What happens:

1. `mongo` starts and must pass its health check (`ping`).
2. `app` image is built, `collectstatic` copies CSS into the shared `book-tracker-static` volume, and Gunicorn starts on `0.0.0.0:8000` inside the Docker network.
3. `nginx` starts and publishes port 8082.

Check the status:

```bash
docker compose ps
```

Expected: three containers `Up`, with mongo marked `(healthy)`.

## 4. Load sample data (first deployment only)

```bash
docker compose exec app python manage.py seed_books
```

It only inserts data when the `books` collection is empty.

## 5. Verify the deployment

**a. Django → MongoDB**

```bash
docker compose exec app python manage.py check_mongo
```

```text
Connected to MongoDB.
  Server version : 7.0.x
  Database       : book_tracker
  Books stored   : 6
```

**b. Browser → Nginx → Gunicorn → Django**

Open <http://localhost:8082> (or <http://127.0.0.1:8082>; always use `http://`, not `https://`). The dashboard shows the totals. Or with curl:

```bash
curl -I http://localhost:8082/                          # 200 OK
curl -I http://localhost:8082/static/books/style.css    # 200 OK, "Server: nginx" (served by Nginx directly)
```

**c. Production settings check** (HTTPS-related warnings are expected while serving plain HTTP)

```bash
docker compose exec app python manage.py check --deploy
```

---

## Day-to-day operations

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Stop (keeps data) | `docker compose stop` |
| Start again | `docker compose start` |
| Restart everything | `docker compose restart` |
| Restart only Django/Gunicorn | `docker compose restart app` |
| Follow logs (all) | `docker compose logs -f` |
| Logs of one service | `docker compose logs -f app` (or `nginx`, `mongo`) |
| Remove containers (keeps data volume) | `docker compose down` |
| Open a MongoDB shell | `docker compose exec mongo mongosh -u USER -p PASS --authenticationDatabase admin book_tracker` |

### Deploying a code change

Code is copied into the image at build time, so rebuild after any change:

```bash
docker compose up -d --build
```

Only the `app` container is rebuilt and replaced; MongoDB data is untouched.

### Changing environment variables

Edit `deploy/docker.env`, then recreate the containers so they pick up the new values (`restart` alone does **not** reload `env_file`):

```bash
docker compose up -d --force-recreate
```

### Backups

```bash
# Backup to ./backup.archive
docker compose exec -T mongo mongodump -u USER -p PASS --authenticationDatabase admin --db book_tracker --archive > backup.archive

# Restore
docker compose exec -T mongo mongorestore -u USER -p PASS --authenticationDatabase admin --archive --drop < backup.archive
```

### Removing everything

```bash
docker compose down            # containers + network
docker compose down -v         # ALSO deletes the MongoDB data and static volumes, so all books are lost
```

---

## Running Django locally against the Docker MongoDB

MongoDB is published on `127.0.0.1:27017`, so you can run Django with `runserver` on your machine and use the same database. In `book_tracker/.env`:

```text
MONGODB_URI=mongodb://USER:PASS@localhost:27017/?authSource=admin
MONGODB_DATABASE=book_tracker
```

```bash
python manage.py check_mongo
python manage.py runserver        # http://127.0.0.1:8000
```

To keep MongoDB completely internal (recommended on a public server), delete the `ports:` section of the `mongo` service.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Bad Request (400)` in the browser | The host you typed isn't in `DJANGO_ALLOWED_HOSTS`. Add it and run `docker compose up -d --force-recreate`. |
| `Forbidden (403) CSRF verification failed` on forms | Add the exact origin (scheme + host + port) to `DJANGO_CSRF_TRUSTED_ORIGINS`, then recreate. |
| Dashboard says *"Could not reach MongoDB"* | Check `MONGODB_URI` (host must be `mongo`), and `docker compose logs mongo`. |
| `Authentication failed` from MongoDB | The `MONGO_INITDB_*` values only apply to a **new** volume. Use the original password, or reset with `docker compose down -v` (deletes data). |
| `502 Bad Gateway` | Gunicorn isn't running: `docker compose logs app`. |
| Page has no styling | `docker compose logs app` should show `static files copied`; rebuild with `docker compose up -d --build`. |
| `http://localhost:8082` hangs but `http://127.0.0.1:8082` works (Windows) | Docker Desktop's WSL2 relay can hang on IPv6 (`::1`), which browsers try first for `localhost`. Keep the port published as `"0.0.0.0:8082:80"` (IPv4 only), as in `docker-compose.yml`, or use `127.0.0.1`. |
| `port is already allocated` | Port 8082 or 27017 is in use. Change the host port in `docker-compose.yml`. |

## Going to production on a public server

- Use strong values for `MONGO_INITDB_ROOT_PASSWORD` and `DJANGO_SECRET_KEY`.
- Set `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` to your domain.
- Remove the `ports:` of the `mongo` service.
- Put HTTPS in front (e.g. change Nginx to listen on 443 with certificates from Let's Encrypt), then set `SECURE_SSL_REDIRECT`, `CSRF_COOKIE_SECURE` and `SECURE_HSTS_SECONDS` in Django settings.
