#!/usr/bin/env bash
set -euo pipefail

# clone-vhost.sh: Clone a WebTonify WordPress vhost
# Usage: ./clone-vhost.sh [-new] source.tld dest.tld

NEW_MODE=false
if [[ ${1:-} == "-new" ]]; then
  NEW_MODE=true
  shift
fi

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 [-new] <source-domain> <dest-domain>"
  exit 1
fi

SRC="$1"
DEST="$2"
USER="gabriel"
EMAIL="gabriel.teodor@webtonify.com"

# 1) Prompt for password only
read -s -p "Enter admin password for ${USER}: " PASS
echo
if [[ -z "$PASS" ]]; then
  echo "Error: password cannot be empty."
  exit 1
fi

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "Error: this script must be run as root"
  exit 1
fi

# Check source exists
if ! wo site info "$SRC" &>/dev/null; then
  echo "Error: source site '$SRC' not found"
  exit 1
fi

# Prevent overwriting an existing dest
if wo site info "$DEST" &>/dev/null; then
  echo "Error: destination site '$DEST' already exists"
  exit 1
fi

# 1. Create vhost+DB only (no WP files)
echo "Creating vhost and DB for $DEST…"
wo site create "$DEST" --wp --php84 --le --user="$USER" --pass="$PASS" --email="$EMAIL" --vhostonly --force

# Paths
SRC_ROOT="/var/www/${SRC}/htdocs"
DEST_ROOT="/var/www/${DEST}/htdocs"
BACKUP_SQL="/tmp/${SRC//./_}.sql"
MYSQL_CONF=/etc/mysql/conf.d/my.cnf

CONF_SRC="/var/www/${SRC}/wp-config.php"
CONF_DEST="/var/www/${DEST}/wp-config.php"

# check if configs are readable
if [[ ! -r "$CONF_SRC" ]]; then
  echo "Error: cannot read source wp-config at $CONF_SRC"
  exit 1
fi

if [[ ! -r "$MYSQL_CONF" ]]; then
  echo "Error: cannot read MySQL config at $MYSQL_CONF"
  exit 1
fi

# 2. Extract DB config for SRC and DEST from wp-config.php
DB_NAME_SRC=$(grep "DB_NAME"    "$CONF_SRC" | cut -d"'" -f4)
DB_USER_SRC=$(grep "DB_USER"    "$CONF_SRC" | cut -d"'" -f4)
DB_PASS_SRC=$(grep "DB_PASSWORD" "$CONF_SRC" | cut -d"'" -f4)
DB_HOST_SRC=$(grep "DB_HOST"    "$CONF_SRC" | cut -d"'" -f4)

DB_NAME_DEST=$(grep "DB_NAME"    "$CONF_DEST" | cut -d"'" -f4)
DB_USER_DEST=$(grep "DB_USER"    "$CONF_DEST" | cut -d"'" -f4)
DB_PASS_DEST=$(grep "DB_PASSWORD" "$CONF_DEST" | cut -d"'" -f4)
DB_HOST_DEST=$(grep "DB_HOST"    "$CONF_DEST" | cut -d"'" -f4)

echo "Source DB: $DB_NAME_SRC"
echo "Destination DB: $DB_NAME_DEST"

# 3. Dump source DB
echo "Exporting database from '$SRC'…"
mariadb-dump \
  --defaults-extra-file="$MYSQL_CONF" \
  --single-transaction \
  --quick \
  --add-drop-table \
  --hex-blob \
  "$DB_NAME_SRC" \
> "$BACKUP_SQL"

# 4. Import into dest DB
echo "Importing into '$DEST'…"
mariadb --defaults-extra-file="$MYSQL_CONF" "$DB_NAME_DEST" < "$BACKUP_SQL"

# 5. Copy all files
echo "Copying files from $SRC to $DEST…"
rsync -a --delete "$SRC_ROOT"/ "$DEST_ROOT"/

# 6. Search-replace URLs in new site
echo "Running WP-CLI search-replace…"
wp search-replace "$SRC" "$DEST" \
  --path="$DEST_ROOT" --all-tables --allow-root

# 7. Fix ownership
echo "Setting file permissions…"
chown -R www-data:www-data "$DEST_ROOT"

if [[ "$NEW_MODE" == false ]]; then
  cp "$CONF_SRC" "$CONF_DEST"
  
  sed -i \
  -e "s/define('DB_NAME'.*/define('DB_NAME', '\$DB_NAME');/" \
  -e "s/define('DB_USER'.*/define('DB_USER', '\$DB_USER');/" \
  -e "s/define('DB_PASSWORD'.*/define('DB_PASSWORD', '\$DB_PASSWORD');/" \
  -e "s/define('DB_HOST'.*/define('DB_HOST', '\$DB_HOST');/" \
  "$CONF_DEST"

  chown www-data:www-data "$CONF_DEST"
  echo "✅ wp-config.php updated for '$DEST'"
fi
# 8. Cleanup
rm -f "$BACKUP_SQL"

echo "✅ Successfully cloned '$SRC' → '$DEST'"
