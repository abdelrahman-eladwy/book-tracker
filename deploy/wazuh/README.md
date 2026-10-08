# Wazuh monitoring for Book Tracker

Wazuh 4.14.8 (manager, indexer, dashboard) runs in Docker on the Jenkins node,
next to the app that the pipeline deploys. A Wazuh agent on the same host
collects the app containers' logs and Docker events.

```
bt-nginx ─┐                                    ┌─ wazuh.manager (rules: built-in web + book_tracker_rules.xml)
bt-app   ─┼─ journald (tags nginx,      ─► agent ─►  wazuh.indexer
bt-mongo ─┘   book-tracker, mongod)     (host)     └─ wazuh.dashboard  https://<host>  (port 443)
Docker events ─────────────── docker-listener ─┘
```

| Source | How it gets there | What alerts |
|---|---|---|
| `bt-nginx` access/error log | journald, tag `nginx` | Wazuh's built-in web rules: SQL injection, XSS, path traversal, scanners, bursts of 4xx/5xx from one IP |
| `bt-app` (Django + Gunicorn) | journald, tag `book-tracker`; Django logging in `book_tracker/settings.py` | CSRF failures, disallowed Host headers, other `django.security` warnings, 500 errors, Gunicorn errors/worker timeouts (rules 100200-100211) |
| `bt-mongo` | journald, tag `mongod` (MongoDB's JSON log) | Authentication failures and brute force, MongoDB errors (rules 100220-100224) |
| Docker | agent `docker-listener` wodle | Containers started/stopped/killed, `docker exec` into containers |
| Host | agent defaults | File integrity, SCA (CIS checks), package vulnerabilities, sshd/sudo logins |

The Jenkins deploy (`Jenkinsfile`) runs the containers with
`--log-driver journald --log-opt tag=...` and turns Gunicorn's access log off
(Nginx already logs every request). `docker logs` still works.

## Install

Requirements: about 15 GB free disk on the Docker disk and 8 GB RAM. Port 443
must be free.

```bash
sudo bash deploy/wazuh/install-wazuh.sh
```

The script:

1. Clones `wazuh-docker` v4.14.8 into `/opt/wazuh-docker`, replaces the default
   passwords with random ones (saved in `/opt/wazuh-docker/single-node/wazuh-passwords.txt`,
   root only) and keeps the indexer (9200), API (55000) and agent ports
   (1514/1515) on localhost. Only the dashboard (443) is reachable from the network.
2. Adds `book_tracker_decoders.xml` and `book_tracker_rules.xml` to the manager.
3. Starts the stack and installs `wazuh-agent` 4.14.8 on the host, enrolled
   with the local manager, with the Docker listener enabled.

Then run a full Jenkins build (**Build Now**) so the app containers are
recreated with journald logging. `bt-mongo` is recreated as well; its data is
in the `bt-mongo-data` volume and is kept.

Open `https://<host-ip>` and log in as `admin` with the password from
`sudo cat /opt/wazuh-docker/single-node/wazuh-passwords.txt`.

If the disk is too small, the script stops and prints the `lvextend` command
that adds the LVM volume group's free space to `/`.

## Check that it works

Generate some events against the deployed app (port 8081):

```bash
curl -s -o /dev/null "http://localhost:8081/books/?q=1%27%20union%20select%20password%20from%20users--"   # SQL injection
curl -s -o /dev/null "http://localhost:8081/books/?q=%3Cscript%3Ealert(1)%3C/script%3E"                     # XSS
for i in $(seq 1 20); do curl -s -o /dev/null "http://localhost:8081/wp-login$i.php"; done                 # 404 scan
curl -s -o /dev/null -H "Host: evil.example" http://localhost:8081/                                         # DisallowedHost
curl -s -o /dev/null -X POST http://localhost:8081/books/add/                                               # CSRF failure
for i in $(seq 1 5); do sudo docker exec bt-mongo mongosh --quiet -u booktracker -p wrong \
    --authenticationDatabase book_tracker --eval 'db.runCommand({ping: 1})' >/dev/null 2>&1; done        # MongoDB brute force
```

In the dashboard, open **Threat Hunting** for the agent and filter on
`rule.groups: book_tracker` or `rule.groups: web`.

To test a log line without generating traffic, use `wazuh-logtest` on the manager:

```bash
cd /opt/wazuh-docker/single-node
sudo docker compose exec wazuh.manager /var/ossec/bin/wazuh-logtest
```

and paste, for example:

```
Oct  8 13:04:43 myhost book-tracker[1234]: WARNING django.security.csrf: Forbidden (CSRF cookie not set.): /books/add/
Oct  8 13:04:43 myhost nginx[1234]: 172.18.0.1 - - [08/Oct/2026:13:04:43 +0000] "GET /books/?q=1'%20union%20select%20password HTTP/1.1" 400 154 "-" "curl/8.5.0" "-"
```

## Operations

- **Change rules or decoders:** edit the XML files here and re-run the install
  script. It copies them and restarts the manager.
- **Stack:** `cd /opt/wazuh-docker/single-node && sudo docker compose ps | logs | restart`.
- **Agent:** `sudo systemctl status wazuh-agent`; its config is `/var/ossec/etc/ossec.conf`.
- **Upgrades:** the agent package is held (`apt-mark hold wazuh-agent`) because
  it must not be newer than the manager. Upgrade the manager first.
- **Blocking attackers:** Wazuh's `firewall-drop` active response does not help
  here. Docker-published ports bypass the host's INPUT chain, so blocking would
  need rules in the `DOCKER-USER` chain.
