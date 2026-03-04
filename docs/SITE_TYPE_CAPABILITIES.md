# Site Type Capabilities (Code-Accurate)

This document focuses on what the current code actually supports for non-WordPress and WordPress site modes.

Primary sources:
- `wo/cli/plugins/site_create.py`
- `wo/cli/plugins/site_update.py`
- `wo/cli/plugins/site_clone.py`
- `wo/cli/plugins/site_backup.py`
- `wo/cli/plugins/site_restore.py`
- `wo/cli/plugins/site_autoupdate.py`
- `wo/cli/plugins/site_functions.py`
- `wo/cli/templates/virtualconf.mustache`

## Site Modes

### `html` (static site)
- Create flags:
  - `wo site create <domain> --html`
  - default when no type flags are provided
- Nginx behavior:
  - `root <webroot>/htdocs`
  - `location / { try_files $uri $uri/ =404; }`
- Runtime:
  - No WordPress install.
  - No database provisioning.
  - You deploy static files to `<webroot>/htdocs`.

### `php` (custom PHP site)
- Create flags:
  - `wo site create <domain> --php [--php74|--php80|--php81|--php82|--php83|--php84]`
- Nginx behavior:
  - Includes `common/php.conf`.
  - Requests are routed to per-site PHP-FPM socket.
- Runtime:
  - No WordPress install.
  - No database provisioning unless you use `--mysql`.
  - You deploy your PHP app to `<webroot>/htdocs`.

### `mysql` (custom PHP + DB helper mode)
- Create flags:
  - `wo site create <domain> --mysql [--php74|...|--php84]`
- Nginx behavior:
  - Same PHP handler path as `php` mode (`common/php.conf`).
- Runtime:
  - Creates database and database user.
  - Writes DB constants to `<webroot>/wo-config.php`.
  - Does not install WordPress unless WP flags are used.

### `proxy` (reverse proxy)
- Create flags:
  - `wo site create <domain> --proxy <host[:port]>`
  - Port defaults to `80` when omitted.
- Nginx behavior:
  - `location / { proxy_pass http://<host>:<port>; ... }`
- Runtime:
  - No WordPress install.
  - No database provisioning.
  - Useful as frontend reverse proxy vhost.

### `alias` (redirect vhost)
- Create flags:
  - `wo site create <domain> --alias <target_domain>`
- Nginx behavior:
  - Returns `301 https://<target_domain>$request_uri`.
- Runtime:
  - No WordPress install.
  - No database provisioning.

### WordPress modes
- `wp`, `wpsubdir`, `wpsubdomain` and cache variants (`wpfc`, `wpsc`, `wprocket`, `wpce`, `wpredis`) are supported and documented in:
  - `docs/WORDPRESS_TEMPLATE_USAGE.md`
  - `docs/AUTOUPDATE_USAGE.md`

## Lifecycle Capability Matrix

Legend:
- `Yes`: implemented and intended
- `Partial`: implemented with limitations
- `No`: blocked by controller logic

| Site type | Create | Update | Backup | Restore | Clone | Autoupdate |
|---|---|---|---|---|---|---|
| `html` | Yes | Partial | Yes | Yes | No | No |
| `php` | Yes | Yes | Yes | Yes | No | No |
| `mysql` | Yes | Yes | Yes | Yes | No | No |
| `proxy` | Yes | Yes | Yes | Partial | No | No |
| `alias` | Yes | Yes | Yes | Partial | No | No |
| `wp` | Yes | Yes | Yes | Yes | Yes | Yes |
| `wpsubdir`/`wpsubdomain` | Yes | Yes | Yes | Yes | Yes | Yes |

## Important Non-WordPress Notes

### 1. `wo site update --html` is not a normal transition path
- The argument exists, but update flow does not build a full conversion path back to `html` in the same way as `php/mysql/wp`.
- In practice, treat `--html` in update as unsupported for reliable type conversion.

### 2. Restore fidelity for `proxy` and `alias` is partial
- Backup metadata (`vhost.json`) stores site type and generic fields.
- Restore reconstructs vhost data from generic fields and does not restore proxy host/port or alias target from dedicated metadata fields.
- Result: restoring proxy/alias archives may not reproduce original proxy/alias routing exactly.

### 3. App deployment expectations for non-WordPress sites
- `html`:
  - place static files in `/var/www/<domain>/htdocs`.
- `php`:
  - place PHP app code in `/var/www/<domain>/htdocs`.
- `mysql`:
  - same as `php`, plus use generated `/var/www/<domain>/wo-config.php` DB values or your own configuration strategy.

### 4. Backups are generic across all site types
- `wo site backup` uses `WOBackup` and can create:
  - full backup
  - db-only backup
  - files-only backup
- Output archive format:
  - `<timestamp>.tar.zst` with `vhost.json`, optional SQL dump, and files.

## Practical Non-WordPress Examples

```bash
# Static site
wo site create static.example.com --html

# PHP app on PHP 8.4
wo site create app.example.com --php --php84

# PHP + MySQL app on PHP 8.3
wo site create api.example.com --mysql --php83

# Reverse proxy to upstream app
wo site create edge.example.com --proxy 127.0.0.1:3000

# Redirect domain
wo site create old.example.com --alias new.example.com
```

## Where to Extend for New Site Modes

If you want to add or improve non-WordPress deployment modes:
- Parse/validate flags:
  - `detSitePar()` and `determine_site_type()` in `site_functions.py`
- Build vhost render context:
  - `site_create.py` and `site_update.py`
- Render behavior:
  - `virtualconf.mustache` and related `common/*.conf` includes
- Persistence:
  - `SiteDB` model and `sitedb.py`
- Backup/restore metadata coverage:
  - `collect_site_metadata()` and `site_restore.py`
