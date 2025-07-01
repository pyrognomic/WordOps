#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# Script to wire up a WebTonify site with its own PHP-FPM pool.
# Idempotent: safe to re-run.
# Usage:
#   sudo ./main.sh yourdomain.com          # setup users, php pool and permissions for domain
#   sudo ./main.sh yourdomain.com --del    # delete/cleanup all related resources
# WO install: wget -qO wo wops.cc && sudo bash wo
# WO Stack install: wo stack install --nginx --php --mariadb --redis --wpcli --fail2ban
# Create site: wo site create domain.com --wpfc --php84 --le --user='xxx' --pass='xxx' --email='x@x.com'
# https://imunify360.com/imunify360-demo/
# https://github.com/rfxn/linux-malware-detect?tab=readme-ov-file
# https://perishablepress.com/ng-firewall/
# https://docs.WebTonify.net/guides/manage-ssl-certificates/
# https://kb.virtubox.net/knowledgebase/cloudflare-ssl-origin-certificates-nginx/
# https://www.youtube.com/watch?v=VOA_H08Bkws
# ------------------------------------------------------------

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 yourdomain.com [--del]" >&2
  exit 1
fi

DELETE_MODE=false
if [[ ${2-} == "--del" ]]; then
  DELETE_MODE=true
fi

DOMAIN="$1"
SLUG="${DOMAIN//./-}"                 # relplace . with -
SLUG="${SLUG,,}"                      # sub.example.com → sub-example-com

PHPVER=$(php -r 'echo PHP_VERSION;' | cut -d. -f1-2)
PHPVER_STRIPPED=${PHPVER//./}

PHP_FPM_DIR="/etc/php/${PHPVER}/fpm"
PHP_LOG_DIR="/var/log/php/${PHPVER}/${SLUG}"

PHP_MASTER_PID="/run/php/php${PHPVER}-fpm-${SLUG}.pid"
PHP_MASTER_CONF_FILE="${PHP_FPM_DIR}/php-fpm-${SLUG}.conf"
PHP_MASTER_LOG_FILE=${PHP_LOG_DIR}/error.log

PHP_POOL_SOCK="/run/php/php${PHPVER}-fpm-${SLUG}.sock"
PHP_POOL_CONF_FILE="${PHP_FPM_DIR}/custom-pool.d/${SLUG}.conf"
PHP_POOL_ACCESS_LOG_FILE=${PHP_LOG_DIR}/access.log
# PHP_POOL_ERROR_LOG_FILE=${PHP_LOG_DIR}/pool-error.log
PHP_POOL_SLOW_LOG_FILE=${PHP_LOG_DIR}/slow.log

PHPFPM_USER="php-${SLUG}"

SYSTEMD_UNIT="php${PHPVER}-fpm@${SLUG}.service"
PHP_FPM_SYSTEMD_TPL="/etc/systemd/system/php${PHPVER}-fpm@.service"

NGINXROOT="/etc/nginx"

WEBROOT="/var/www/${DOMAIN}"
HTDOCS="${WEBROOT}/htdocs"
LOG_DIR="${WEBROOT}/logs"

WPCLI_USER="wpcli-${SLUG}"

SELFSIGNCERT_ROOT="/etc/ssl/selfsigned"
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1) Must be root
if (( EUID != 0 )); then
  echo "Error: this script must be run as root" >&2
  exit 1
fi

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

# cleanup function
cleanup() {
  echo "Cleaning up resources for ${DOMAIN}..."

  systemctl stop "${SYSTEMD_UNIT}" || true
  systemctl disable "${SYSTEMD_UNIT}" || true
  systemctl daemon-reload

  rm -f "${PHP_MASTER_CONF_FILE}"
  rm -rf "${PHP_LOG_DIR}"
  rm -f "${NGINXROOT}/sites-enabled/${DOMAIN}" \
        "${NGINXROOT}/sites-available/${DOMAIN}"
  rm -f "${NGINXROOT}/conf.d/upstream-${SLUG}.conf" \
        "${NGINXROOT}/common/php${PHPVER_STRIPPED}-${SLUG}.conf" \
        "${NGINXROOT}/common/wpcommon-php${PHPVER_STRIPPED}-${SLUG}.conf"

  # remove nginx from php-fpm group and php-fpm user from wp-cli group
  gpasswd -d www-data "${PHPFPM_USER}" || true
  gpasswd -d "${PHPFPM_USER}" "${WPCLI_USER}" || true

  # delete users and groups
  userdel "${PHPFPM_USER}" || true
  userdel "${WPCLI_USER}" || true
  groupdel "${PHPFPM_USER}" || true
  groupdel "${WPCLI_USER}" || true
  echo "Done cleanup for ${DOMAIN}."
  exit 0
}

# if delete mode, run cleanup and exit
echo
if $DELETE_MODE; then
  cleanup
fi

# 2) Ensure directories exist
mkdir -p "$WEBROOT" "$HTDOCS" "$LOG_DIR" "$PHP_LOG_DIR" "$PHP_FPM_DIR/custom-pool.d" /run/php $SELFSIGNCERT_ROOT

# 3) Create service accounts if missing
if ! id "$WPCLI_USER" &>/dev/null; then
  useradd -r -d "$HTDOCS" -s /usr/sbin/nologin "$WPCLI_USER"
fi
if ! id "$PHPFPM_USER" &>/dev/null; then
  useradd -r -M -d /nonexistent -s /usr/sbin/nologin "$PHPFPM_USER"
fi

# 4) Let nginx (www-data) read the Wordpress files (add nginx user to the php-fpm pool user)
usermod -aG "$PHPFPM_USER" www-data

# 5) Let php-fpm read wp-config.php which is outside the Wordpress folder
usermod -aG "$WPCLI_USER" "$PHPFPM_USER"

# 6) Set ownership: wpcli-user owns Wordpress files, php-fpm group r-x
chown -R "$WPCLI_USER":"$PHPFPM_USER" "$HTDOCS"

# 7) Give read permissions to php-fpm user for wp-config.php outside of the Wordpress installation dir
chown -R "$WPCLI_USER":"$WPCLI_USER" "$WEBROOT/wp-config.php"
chmod 640 "$WEBROOT/wp-config.php"

# 8) Default perms: PHP-FPM can read/traverse, but cannot write
find "$HTDOCS" \
  -path "$HTDOCS/wp-content/uploads"   -prune \
  -o -path "$HTDOCS/wp-content/cache"      -prune \
  -o -path "$HTDOCS/wp-content/languages"  -prune \
  -o -path "$HTDOCS/wp-content/upgrade"    -prune \
  -o -type d -exec chmod 750 {} + \
  -o -type f -exec chmod 640 {} +

# 7) Enable write only in the dynamic dirs
for d in uploads cache languages upgrade; do
  D="$HTDOCS/wp-content/$d"
  mkdir -p "$D"
  chown "$WPCLI_USER":"$PHPFPM_USER" "$D"
  find "$D" -type d -exec chmod 770 {} +  # rwx for owner+group
  find "$D" -type f -exec chmod 660 {} +  # rw for owner+group
done

export \
  PHPVER \
  PHP_MASTER_PID \
  PHP_MASTER_LOG_FILE \
  PHP_POOL_CONF_FILE \
  PHPFPM_USER \
  PHP_POOL_SOCK \
  PHP_POOL_ACCESS_LOG_FILE \
  PHP_POOL_SLOW_LOG_FILE \
  WEBROOT \
  DOMAIN \
  HTDOCS \
  PHPVER_STRIPPED \
  SLUG \
  SELFSIGNCERT_ROOT

if [[ ! -f "${PHP_FPM_SYSTEMD_TPL}" ]]; then
  run_render '${PHPVER}' "${TEMPLATE_DIR}/php-fpm-systemd.tpl" "${PHP_FPM_SYSTEMD_TPL}"
fi

# 8) Write the per-site PHP-FPM global config
run_render '${PHP_MASTER_PID} ${PHP_MASTER_LOG_FILE} ${PHP_POOL_CONF_FILE}' \
  "${TEMPLATE_DIR}/php-fpm-master.tpl" "${PHP_MASTER_CONF_FILE}"

# 9) Write the per-site pool config
run_render '${PHPFPM_USER} ${PHP_POOL_SOCK} ${PHP_POOL_ACCESS_LOG_FILE} ${PHP_POOL_SLOW_LOG_FILE} ${SLUG} ${WEBROOT}' \
  "${TEMPLATE_DIR}/php-fpm-pool.tpl" "${PHP_POOL_CONF_FILE}"

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

# 11) define individual php upstream for each website
run_render '${PHPVER_STRIPPED} ${SLUG} ${PHP_POOL_SOCK}' \
  "${TEMPLATE_DIR}/nginx_upstream.tpl" "${NGINXROOT}/conf.d/upstream-${SLUG}.conf"

# nginx php proxy pass to dedicated php upstream
run_render '${PHPVER_STRIPPED} ${SLUG}' \
  "${TEMPLATE_DIR}/nginx_php_proxy.tpl" "${NGINXROOT}/common/php${PHPVER_STRIPPED}-${SLUG}.conf"

# additional nginx configs
run_render '${PHPVER_STRIPPED} ${SLUG}' \
  "${TEMPLATE_DIR}/nginx_additional_config.tpl" "${NGINXROOT}/common/wpcommon-php${PHPVER_STRIPPED}-${SLUG}.conf"

# nginx setup vhost
run_render '${PHPVER_STRIPPED} ${SLUG} ${DOMAIN} ${HTDOCS} ${WEBROOT}' \
  "${TEMPLATE_DIR}/nginx_vhost.tpl" "${NGINXROOT}/sites-available/${DOMAIN}"

ln -sf "${NGINXROOT}/sites-available/${DOMAIN}" "${NGINXROOT}/sites-enabled/${DOMAIN}"

# 12) Enable & start the systemd instance
systemctl daemon-reload
systemctl enable "${SYSTEMD_UNIT}"
systemctl start "${SYSTEMD_UNIT}"

if ! systemctl is-active --quiet php${PHPVER}-fpm@"${SLUG}".service; then
  echo "❌ php-fpm@${SLUG} failed to start" >&2
  journalctl -u php${PHPVER}-fpm@"${SLUG}" --no-pager
  exit 1
fi

if ! nginx -t -q; then
  echo "❌ nginx config test failed, aborting" >&2
  exit 1
fi

systemctl restart nginx

echo "✔ php${PHPVER}-fpm@${SLUG} is running with its own pool."
echo "  - Socket:    /run/php/php${PHPVER}-fpm-${SLUG}.sock"
echo "  - Logs:      ${LOG_DIR}/php-fpm-*.log"
echo "  - Files:     ${WEBROOT} (owned ${WPCLI_USER}:${PHPFPM_USER})"
echo "  - WP Config: ${WEBROOT} (owned ${WPCLI_USER}:${WPCLI_USER})"
