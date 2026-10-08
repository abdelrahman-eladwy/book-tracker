#!/usr/bin/env bash
# Deploy Wazuh (single node, Docker) on this host and connect it to the
# Book Tracker deployment made by the Jenkins pipeline.
#
#   sudo bash deploy/wazuh/install-wazuh.sh
#
# Safe to re-run: it keeps the generated passwords and certificates, and
# re-copies the Book Tracker rules/decoders (restarting the manager to load them).
# See deploy/wazuh/README.md.
set -euo pipefail

WAZUH_VERSION=4.14.8
WAZUH_DIR=/opt/wazuh-docker
SN="$WAZUH_DIR/single-node"
PASSWORDS="$SN/wazuh-passwords.txt"
HERE="$(cd "$(dirname "$0")" && pwd)"
MIN_FREE_GB=15

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

# --- Preflight ----------------------------------------------------------------

free_gb=$(df -BG --output=avail /var/lib/docker | tail -n 1 | tr -dc '0-9')
if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
    echo "Only ${free_gb}G free on the Docker disk; Wazuh needs about ${MIN_FREE_GB}G (images + data)."
    vg_free=$(vgs --noheadings --units g -o vg_free 2>/dev/null | head -n 1 | tr -d ' ')
    if [ -n "$vg_free" ]; then
        echo "The LVM volume group has ${vg_free} unallocated. To add it to / (online, no reboot):"
        echo "  sudo lvextend -r -l +100%FREE $(findmnt -no SOURCE /)"
    fi
    exit 1
fi

mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
[ "$mem_gb" -ge 7 ] || echo "WARNING: ${mem_gb}G RAM; Wazuh recommends 8G. Continuing anyway."

if ss -ltnH '( sport = :443 )' | grep -q .; then
    if ! docker ps --format '{{.Names}}' | grep -q 'wazuh.dashboard'; then
        echo "Port 443 is already in use; the Wazuh dashboard needs it."
        exit 1
    fi
fi

# The indexer (OpenSearch) needs a high mmap count.
if [ "$(sysctl -n vm.max_map_count)" -lt 262144 ]; then
    sysctl -w vm.max_map_count=262144
    echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-wazuh.conf
fi

command -v git >/dev/null || apt-get install -y git

# --- Wazuh server (manager + indexer + dashboard) -----------------------------

if [ ! -d "$WAZUH_DIR" ]; then
    git clone --depth 1 -b "v$WAZUH_VERSION" https://github.com/wazuh/wazuh-docker.git "$WAZUH_DIR"
fi
cd "$SN"

if [ ! -f "$PASSWORDS" ]; then
    echo "Generating passwords..."
    # Letters, digits and '.' only: safe in YAML, Compose and URIs, and meets the
    # Wazuh API policy (upper, lower, digit, symbol).
    ADMIN_PW="$(openssl rand -hex 16)Aa1."
    KIBANA_PW="$(openssl rand -hex 16)Aa1."
    API_PW="$(openssl rand -hex 16)Aa1."

    hash_pw() {
        docker run --rm "wazuh/wazuh-indexer:$WAZUH_VERSION" \
            bash /usr/share/wazuh-indexer/plugins/opensearch-security/tools/hash.sh -p "$1" | tail -n 1
    }
    ADMIN_HASH=$(hash_pw "$ADMIN_PW")
    KIBANA_HASH=$(hash_pw "$KIBANA_PW")
    case "$ADMIN_HASH$KIBANA_HASH" in
        '$2'*'$2'*) ;;
        *) echo "Could not generate password hashes."; exit 1 ;;
    esac

    # Replace the published default passwords before the first start (the
    # indexer loads internal_users.yml when its security index is created), and
    # keep the indexer, API and agent ports on localhost: only the dashboard
    # (443) is reachable from the network.
    ADMIN_PW="$ADMIN_PW" KIBANA_PW="$KIBANA_PW" API_PW="$API_PW" \
    ADMIN_HASH="$ADMIN_HASH" KIBANA_HASH="$KIBANA_HASH" python3 - <<'EOF'
import os, re

e = os.environ

def edit(path, pairs, regex=False):
    s = open(path).read()
    for old, new in pairs:
        if regex:
            s, n = re.subn(old, lambda m: m.group(1) + new + m.group(2), s, flags=re.M)
        else:
            n = s.count(old)
            s = s.replace(old, new)
        if n == 0:
            raise SystemExit("%s: did not find %r" % (path, old))
    open(path, "w").write(s)

edit("config/wazuh_indexer/internal_users.yml", [
    (r'(^admin:\n  hash: ")[^"]*(")', e["ADMIN_HASH"]),
    (r'(^kibanaserver:\n  hash: ")[^"]*(")', e["KIBANA_HASH"]),
], regex=True)

edit("docker-compose.yml", [
    ("INDEXER_PASSWORD=SecretPassword", "INDEXER_PASSWORD=" + e["ADMIN_PW"]),
    ("DASHBOARD_PASSWORD=kibanaserver", "DASHBOARD_PASSWORD=" + e["KIBANA_PW"]),
    ("API_PASSWORD=MyS3cr37P450r.*-", "API_PASSWORD=" + e["API_PW"]),
    ('"1514:1514"', '"127.0.0.1:1514:1514"'),
    ('"1515:1515"', '"127.0.0.1:1515:1515"'),
    ('"514:514/udp"', '"127.0.0.1:514:514/udp"'),
    ('"55000:55000"', '"127.0.0.1:55000:55000"'),
    ('"9200:9200"', '"127.0.0.1:9200:9200"'),
])

edit("config/wazuh_dashboard/wazuh.yml", [
    ('password: "MyS3cr37P450r.*-"', 'password: "%s"' % e["API_PW"]),  # Wazuh's published default  # pragma: allowlist secret
])
EOF

    umask 077
    cat > "$PASSWORDS" <<EOF
Wazuh dashboard / indexer  user: admin         password: $ADMIN_PW
Dashboard server user      user: kibanaserver  password: $KIBANA_PW
Wazuh API                  user: wazuh-wui     password: $API_PW
EOF
    umask 022
    chmod 600 "$PASSWORDS"
fi

if [ ! -d config/wazuh_indexer_ssl_certs ] || [ -z "$(ls -A config/wazuh_indexer_ssl_certs)" ]; then
    echo "Generating TLS certificates..."
    docker compose -f generate-indexer-certs.yml run --rm generator
fi

# Book Tracker decoders and rules. The manager copies /wazuh-config-mount/* into
# /var/ossec on every start.
install -d -m 755 config/book_tracker
install -m 644 "$HERE/book_tracker_decoders.xml" "$HERE/book_tracker_rules.xml" config/book_tracker/
if ! grep -q 'book_tracker_rules.xml' docker-compose.yml; then
    python3 - <<'EOF'
path = "docker-compose.yml"
s = open(path).read()
anchor = "      - ./config/wazuh_cluster/wazuh_manager.conf:/wazuh-config-mount/etc/ossec.conf\n"
assert s.count(anchor) == 1, "manager ossec.conf mount not found"
s = s.replace(anchor, anchor +
    "      - ./config/book_tracker/book_tracker_decoders.xml:/wazuh-config-mount/etc/decoders/book_tracker_decoders.xml\n"
    "      - ./config/book_tracker/book_tracker_rules.xml:/wazuh-config-mount/etc/rules/book_tracker_rules.xml\n")
open(path, "w").write(s)
EOF
fi

manager_was_running=$(docker compose ps -q --status running wazuh.manager)
docker compose up -d
# A running manager only re-reads the rules when it restarts.
[ -n "$manager_was_running" ] && docker compose restart wazuh.manager

wait_for() {  # wait_for <what> <url> <ok-codes-regex>
    echo -n "Waiting for $1"
    for _ in $(seq 1 120); do
        code=$(curl -sk -o /dev/null -w '%{http_code}' "$2" || true)
        if printf '%s' "$code" | grep -Eq "$3"; then echo " ok"; return 0; fi
        echo -n "."; sleep 5
    done
    echo; echo "$1 did not come up; check: cd $SN && docker compose logs --tail 100"; exit 1
}
wait_for "Wazuh API" https://127.0.0.1:55000/ '^(200|401)$'
wait_for "Wazuh dashboard" https://127.0.0.1/ '^(200|302|401)$'

# --- Wazuh agent on this host --------------------------------------------------
# Reads the host's journald, which is where the Jenkins deploy sends the
# bt-nginx / bt-app / bt-mongo container logs (tags nginx / book-tracker / mongod),
# and watches Docker events (container start/stop/exec...).

if ! dpkg -s wazuh-agent >/dev/null 2>&1; then
    curl -fsSL https://packages.wazuh.com/key/GPG-KEY-WAZUH \
        | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
    chmod 644 /usr/share/keyrings/wazuh.gpg
    echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
        > /etc/apt/sources.list.d/wazuh.list
    apt-get update
    WAZUH_MANAGER=127.0.0.1 WAZUH_AGENT_NAME="$(hostname)" \
        apt-get install -y "wazuh-agent=$WAZUH_VERSION-1"
    # The agent must not be newer than the manager.
    apt-mark hold wazuh-agent
fi

# Python Docker SDK for the docker-listener wodle.
apt-get install -y python3-docker

CONF=/var/ossec/etc/ossec.conf
if ! grep -q 'book-tracker integration' "$CONF"; then
    {
        echo '<!-- book-tracker integration (deploy/wazuh/install-wazuh.sh) -->'
        echo '<ossec_config>'
        echo '  <wodle name="docker-listener">'
        echo '    <disabled>no</disabled>'
        echo '    <interval>10m</interval>'
        echo '    <attempts>5</attempts>'
        echo '    <run_on_start>yes</run_on_start>'
        echo '  </wodle>'
        # Container logs reach the agent through journald or, when the agent
        # reads /var/log/syslog instead, through journald's syslog forwarding.
        # Only add a journald reader when neither is configured, so nothing is
        # read twice.
        if ! grep -q '<location>journald</location>' "$CONF" && ! grep -q '/var/log/syslog' "$CONF"; then
            echo '  <localfile>'
            echo '    <location>journald</location>'
            echo '    <log_format>journald</log_format>'
            echo '  </localfile>'
        fi
        echo '</ossec_config>'
    } >> "$CONF"
fi

systemctl daemon-reload
systemctl enable wazuh-agent >/dev/null
systemctl restart wazuh-agent

echo -n "Waiting for the agent to connect"
for _ in $(seq 1 24); do
    if docker compose exec -T wazuh.manager /var/ossec/bin/agent_control -l 2>/dev/null | grep -q "Name: $(hostname),.*Active"; then
        echo " ok"; break
    fi
    echo -n "."; sleep 5
done

docker compose exec -T wazuh.manager /var/ossec/bin/agent_control -l || true

ip=$(hostname -I | awk '{print $1}')
echo
echo "Wazuh dashboard: https://$ip  (self-signed certificate; the browser will warn)"
echo "Log in as admin; passwords are in $PASSWORDS (root only):"
echo "  sudo cat $PASSWORDS"
echo
echo "Next: run a Jenkins build (Build Now) so the app containers log to journald."
