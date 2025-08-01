#!/usr/bin/env bash
set -euo pipefail
trap 'echo "❌ Cleanup failed" >&2' ERR

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "Error: this script must be run as root"
  exit 1
fi

WEBROOT="/var/www/${DOMAIN}"
NGINXROOT="/etc/nginx"
SELFSIGNCERT_ROOT="/etc/ssl/selfsigned"
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1) Ensure template directory exists
if [[ ! -d "${TEMPLATE_DIR}" ]]; then
  echo "Error: TEMPLATE_DIR='${TEMPLATE_DIR}' not found" >&2
  exit 1
fi

run_render() {
  local vars="$1" src="$2" dst="$3"
  if [[ ! -r "$src" ]]; then
    echo "❌ Missing template $src" >&2
    exit 1
  fi
  if ! envsubst "$vars" < "$src" > "$dst"; then
    echo "❌ Failed to render $src → $dst" >&2
    exit 1
  fi
}

# 2) Ensure directory exists
mkdir -p $SELFSIGNCERT_ROOT

export SELFSIGNCERT_ROOT

# 9) WebTonify admin cleanup
rm -rf "${NGINXROOT}/sites-enabled/22222.conf"
rm -rf "${WEBROOT}/22222"
rm -rf "${WEBROOT}/html/index.nginx-debian.html"

# 10) Catch-all deny
if [[ ! -f "${SELFSIGNCERT_ROOT}/default.crt" ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 \
    -days 365 \
    -keyout ${SELFSIGNCERT_ROOT}/default.key \
    -out ${SELFSIGNCERT_ROOT}/default.crt \
    -subj "/CN=catch-all" \
    -addext "subjectAltName=IP:127.0.0.1,IP:::1"
fi

if [[ ! -f "${NGINXROOT}/conf.d/default-deny.conf" ]]; then
run_render '${SELFSIGNCERT_ROOT}' \
  "${TEMPLATE_DIR}/nginx_default_deny.tpl" "${NGINXROOT}/conf.d/default-deny.conf"
fi

# 12) Enable & start the systemd instance
systemctl daemon-reload
systemctl enable "${SYSTEMD_UNIT}"
systemctl start "${SYSTEMD_UNIT}"

if ! nginx -t -q; then
  echo "❌ nginx config test failed, aborting" >&2
  exit 1
fi

systemctl restart nginx

echo "✅ Successfully created catch-all Nginx configuration."
