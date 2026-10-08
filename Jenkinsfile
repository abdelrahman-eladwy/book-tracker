// Book Tracker CI/CD: Django + Gunicorn + Nginx + MongoDB, all in Docker.
//
// Runs on the Jenkins node itself (Docker must be installed there and the
// jenkins user must be allowed to run `docker`). Tools that are not part of the
// project (Python, pip-audit, Bandit, Grype) are run in throwaway containers, so
// nothing else has to be installed on the node.
//
// Required Jenkins credentials (Kind: "Secret text"):
//   book-tracker-mongo-root-password   MongoDB root password
//   book-tracker-mongo-app-password    password of the app's MongoDB user
//   book-tracker-django-secret-key     Django SECRET_KEY
//   dockerhub-credentials              Kind "Username with password": Docker Hub
//                                      username + access token (not the account password)
// The two MongoDB passwords may only contain letters, digits and . _ -
// (they are placed inside a connection URI).

// Deploy only from main (works for both plain and multibranch pipeline jobs).
def isMain() {
    def branch = env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'main'
    return branch == 'main' || branch == 'origin/main'
}

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
    }

    parameters {
        string(name: 'APP_PORT', defaultValue: '8081', description: 'Host port Nginx is published on')
        string(name: 'APP_HOST', defaultValue: 'localhost', description: 'Hostname/IP users open in the browser (added to ALLOWED_HOSTS and CSRF trusted origins)')
    }

    environment {
        IMAGE_NAME = 'book-tracker'
        IMAGE_TAG  = "build-${env.BUILD_NUMBER}"
        PY_IMAGE   = 'python:3.12-slim'

        NETWORK    = 'bt-net'
        MONGO_NAME = 'bt-mongo'
        APP_NAME   = 'bt-app'
        NGINX_NAME = 'bt-nginx'
        MONGO_VOL  = 'bt-mongo-data'
        STATIC_VOL = 'bt-static'
        MONGODB_DATABASE = 'book_tracker'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // Python is interpreted, so "build" means: install the dependencies and
        // make sure the code compiles and Django's own system checks pass.
        stage('Build') {
            steps {
                sh '''
                    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
                        -e PYTHONDONTWRITEBYTECODE=1 \
                        -v "$WORKSPACE":/src -w /src "$PY_IMAGE" sh -c '
                            python -m venv /tmp/venv &&
                            /tmp/venv/bin/pip install --no-cache-dir -q -r requirements.txt &&
                            /tmp/venv/bin/python -m compileall -q books book_tracker manage.py &&
                            /tmp/venv/bin/python manage.py check
                        '
                '''
            }
        }

        // Scan failures are reported (stage turns red, build becomes UNSTABLE)
        // but do not stop the pipeline.
        stage('Security scans') {
            parallel {
                // SCA: known-vulnerable Python dependencies (PyPA pip-audit).
                stage('SCA (pip-audit)') {
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
                                    -v "$WORKSPACE":/src -w /src "$PY_IMAGE" sh -c '
                                        python -m venv /tmp/venv &&
                                        /tmp/venv/bin/pip install --no-cache-dir -q pip-audit &&
                                        /tmp/venv/bin/pip-audit -r requirements.txt --progress-spinner off \
                                            > pip-audit-report.txt 2>&1
                                        rc=$?
                                        cat pip-audit-report.txt
                                        exit $rc
                                    '
                            '''
                        }
                    }
                }

                // SAST: Bandit, the Python security linter (medium+ severity).
                stage('SAST (Bandit)') {
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
                                    -v "$WORKSPACE":/src -w /src "$PY_IMAGE" sh -c '
                                        python -m venv /tmp/venv &&
                                        /tmp/venv/bin/pip install --no-cache-dir -q bandit &&
                                        /tmp/venv/bin/bandit -r books book_tracker manage.py -ll \
                                            > bandit-report.txt 2>&1
                                        rc=$?
                                        cat bandit-report.txt
                                        exit $rc
                                    '
                            '''
                        }
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: '*-report.txt', allowEmptyArchive: true
                }
            }
        }

        // The image is built on this node and deployed from the local Docker
        // store, so nothing is exported or uploaded anywhere.
        stage('Build Docker image') {
            when { expression { isMain() } }
            steps {
                sh 'docker build -t "$IMAGE_NAME:$IMAGE_TAG" -t "$IMAGE_NAME:latest" .'
            }
        }

        // Image scan with Grype (OS packages + Python packages inside the image).
        stage('Image scan (Grype)') {
            when { expression { isMain() } }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    sh '''
                        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                            anchore/grype:latest "docker:$IMAGE_NAME:$IMAGE_TAG" \
                            --only-fixed --fail-on high
                    '''
                }
            }
        }

        stage('Deploy MongoDB') {
            when { expression { isMain() } }
            steps {
                withCredentials([
                    string(credentialsId: 'book-tracker-mongo-root-password', variable: 'MONGO_INITDB_ROOT_PASSWORD'),
                    string(credentialsId: 'book-tracker-mongo-app-password', variable: 'MONGO_APP_PASSWORD')
                ]) {
                    sh '''
                        for v in "$MONGO_INITDB_ROOT_PASSWORD" "$MONGO_APP_PASSWORD"; do
                            if [ -z "$v" ] || printf '%s' "$v" | grep -q '[^A-Za-z0-9._-]'; then
                                echo "MongoDB passwords must be non-empty and only contain letters, digits and . _ -"
                                exit 1
                            fi
                        done

                        docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"
                        docker volume create "$MONGO_VOL" >/dev/null

                        # The init script creates the least-privilege app user the
                        # first time the (empty) data volume is initialised.
                        if docker inspect "$MONGO_NAME" >/dev/null 2>&1; then
                            docker start "$MONGO_NAME" >/dev/null
                        else
                            docker create --name "$MONGO_NAME" \
                                --network "$NETWORK" \
                                --restart unless-stopped \
                                -e MONGO_INITDB_ROOT_USERNAME=bookadmin \
                                -e MONGO_INITDB_ROOT_PASSWORD \
                                -e MONGO_INITDB_DATABASE="$MONGODB_DATABASE" \
                                -e MONGO_APP_USER=booktracker \
                                -e MONGO_APP_PASSWORD \
                                -v "$MONGO_VOL":/data/db \
                                --health-cmd="mongosh --quiet --eval \\"db.adminCommand('ping')\\"" \
                                --health-interval=5s --health-timeout=5s --health-retries=24 \
                                mongo:7 >/dev/null
                            docker cp deploy/mongo/init-app-user.js "$MONGO_NAME":/docker-entrypoint-initdb.d/01-app-user.js
                            docker start "$MONGO_NAME" >/dev/null
                        fi

                        echo "Waiting for MongoDB to become healthy..."
                        for i in $(seq 1 40); do
                            status=$(docker inspect -f '{{.State.Health.Status}}' "$MONGO_NAME")
                            [ "$status" = "healthy" ] && { echo "MongoDB is healthy."; exit 0; }
                            sleep 3
                        done
                        docker logs --tail 50 "$MONGO_NAME"
                        echo "MongoDB did not become healthy"
                        exit 1
                    '''
                }
            }
        }

        stage('Deploy app (Gunicorn + Nginx)') {
            when { expression { isMain() } }
            steps {
                withCredentials([
                    string(credentialsId: 'book-tracker-mongo-app-password', variable: 'MONGO_APP_PASSWORD'),
                    string(credentialsId: 'book-tracker-django-secret-key', variable: 'DJANGO_SECRET_KEY')
                ]) {
                    sh '''
                        export MONGODB_URI="mongodb://booktracker:${MONGO_APP_PASSWORD}@${MONGO_NAME}:27017/${MONGODB_DATABASE}?authSource=${MONGODB_DATABASE}"
                        export DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,${APP_HOST}"
                        export DJANGO_CSRF_TRUSTED_ORIGINS="http://localhost:${APP_PORT},http://127.0.0.1:${APP_PORT},http://${APP_HOST}:${APP_PORT}"

                        docker rm -f "$NGINX_NAME" "$APP_NAME" >/dev/null 2>&1 || true
                        docker volume create "$STATIC_VOL" >/dev/null

                        # Gunicorn + Django. Not published to the host: Nginx reaches
                        # it as app:8000 on the internal network.
                        docker run -d --name "$APP_NAME" \
                            --network "$NETWORK" --network-alias app \
                            --restart unless-stopped \
                            -e GUNICORN_BIND=0.0.0.0:8000 \
                            -e DJANGO_DEBUG=False \
                            -e DJANGO_STATIC_ROOT=/opt/book_tracker/staticfiles \
                            -e DJANGO_SECRET_KEY \
                            -e DJANGO_ALLOWED_HOSTS \
                            -e DJANGO_CSRF_TRUSTED_ORIGINS \
                            -e MONGODB_URI \
                            -e MONGODB_DATABASE \
                            -v "$STATIC_VOL":/opt/book_tracker/staticfiles \
                            "$IMAGE_NAME:$IMAGE_TAG"

                        # Nginx: the config is copied into the container (not
                        # bind-mounted) so it does not depend on the workspace.
                        docker create --name "$NGINX_NAME" \
                            --network "$NETWORK" \
                            --restart unless-stopped \
                            -p "$APP_PORT":80 \
                            -v "$STATIC_VOL":/opt/book_tracker/staticfiles:ro \
                            nginx:stable >/dev/null
                        docker cp deploy/nginx/docker.conf "$NGINX_NAME":/etc/nginx/conf.d/default.conf
                        docker start "$NGINX_NAME" >/dev/null
                    '''
                }
            }
        }

        stage('Smoke test') {
            when { expression { isMain() } }
            steps {
                sh '''
                    ok=0
                    for i in $(seq 1 20); do
                        code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${APP_PORT}/" || true)
                        echo "GET / -> HTTP $code"
                        [ "$code" = "200" ] && { ok=1; break; }
                        sleep 3
                    done
                    [ "$ok" = "1" ] || { docker logs --tail 50 "$APP_NAME"; exit 1; }

                    # Django -> MongoDB (authenticated connection as the app user)
                    docker exec "$APP_NAME" python manage.py check_mongo
                '''
            }
        }

        // Publish the image only after it has been deployed and passed the smoke test.
        stage('Push to Docker Hub') {
            when { expression { isMain() } }
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'dockerhub-credentials',
                                     usernameVariable: 'DOCKERHUB_USER',
                                     passwordVariable: 'DOCKERHUB_TOKEN')
                ]) {
                    sh '''
                        # Use a throwaway Docker config so the login is not left on the node.
                        export DOCKER_CONFIG="$(mktemp -d)"
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT

                        REPO="$DOCKERHUB_USER/$IMAGE_NAME"
                        printf '%s' "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin

                        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REPO:$IMAGE_TAG"
                        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REPO:latest"
                        docker push "$REPO:$IMAGE_TAG"
                        docker push "$REPO:latest"
                    '''
                }
            }
        }
    }

    post {
        failure {
            sh 'docker ps -a --filter "name=bt-" || true'
        }
        cleanup {
            // Keep only the last few image tags on the node.
            sh '''
                docker images "$IMAGE_NAME" --format '{{.Tag}}' | grep '^build-' | sort -t- -k2 -n -r | tail -n +4 \
                    | xargs -r -I{} docker rmi "$IMAGE_NAME:{}" || true
            '''
        }
    }
}
