#!/usr/bin/env bash
set -euo pipefail
trap 'echo "❌ Cleanup failed" >&2' ERR

# delete.sh: Delete vhost
# Usage: ./delete.sh domain.tld
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <domain>"
  exit 1
fi

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "Error: this script must be run as root"
  exit 1
fi

# check if WordOps is installed
command -v wo >/dev/null || { echo "Error: wordops (wo) not installed"; exit 1; }

DOMAIN="$1"

# Check if VHOST exists
if ! wo site info "$DOMAIN" &>/dev/null; then
  echo "Error: vhost '$DOMAIN' not found"
  exit 1
fi

SLUG="${DOMAIN//./-}"                 # relplace . with -
SLUG="${SLUG,,}"                      # sub.example.com → sub-example-com

# get VHOST php version
PHPVER=$(wo site info "${DOMAIN}" | grep -i 'PHP Version' | awk '{ print $NF }')
PHPVER_STRIPPED=${PHPVER//./}

PHP_FPM_DIR="/etc/php/${PHPVER}/fpm"
PHP_LOG_DIR="/var/log/php/${PHPVER}/${SLUG}"

PHP_MASTER_PID="/run/php/php${PHPVER}-fpm-${SLUG}.pid"
PHP_MASTER_CONF_FILE="${PHP_FPM_DIR}/php-fpm-${SLUG}.conf"

PHP_MASTER_LOG_FILE=${PHP_LOG_DIR}/error.log
PHP_POOL_ACCESS_LOG_FILE=${PHP_LOG_DIR}/access.log
PHP_POOL_SLOW_LOG_FILE=${PHP_LOG_DIR}/slow.log

PHP_POOL_SOCK="/run/php/php${PHPVER}-fpm-${SLUG}.sock"
PHP_POOL_CONF_FILE="${PHP_FPM_DIR}/pool.d/${SLUG}.conf"

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

# START CLEANUP
echo "[WordOps]: Deleting $DOMAIN…"
wo site delete "$DOMAIN"

echo "[Custom]: Cleaning up resources for ${DOMAIN}..."
systemctl stop "${SYSTEMD_UNIT}" || true
systemctl disable "${SYSTEMD_UNIT}" || true
systemctl daemon-reload

rm -rf "${PHP_LOG_DIR}"
rm -f "${NGINXROOT}/sites-enabled/${DOMAIN}" \
      "${NGINXROOT}/sites-available/${DOMAIN}" \
      "${NGINXROOT}/conf.d/upstream-${SLUG}.conf" \
      "${NGINXROOT}/common/php${PHPVER_STRIPPED}-${SLUG}.conf" \
      "${NGINXROOT}/common/wpcommon-php${PHPVER_STRIPPED}-${SLUG}.conf" \
      "${PHP_MASTER_PID}" \
      "${PHP_MASTER_CONF_FILE}" \
      "${PHP_POOL_CONF_FILE}" \
      "${PHP_POOL_SOCK}"

# remove nginx from php-fpm group and php-fpm user from wp-cli group
gpasswd -d www-data "${PHPFPM_USER}" || true
gpasswd -d "${PHPFPM_USER}" "${WPCLI_USER}" || true

# delete users and groups
userdel "${PHPFPM_USER}" || true
userdel "${WPCLI_USER}" || true
groupdel "${PHPFPM_USER}" || true
groupdel "${WPCLI_USER}" || true

nginx -t && systemctl reload nginx

echo "✅ Successfully deleted '$DOMAIN'"
