# WordOps

WordOps is a Python CLI for provisioning and operating Nginx-based websites on Linux.

The current codebase supports more than WordPress:
- Static sites (`--html`)
- PHP sites (`--php`, `--php74`..`--php84`)
- PHP + MySQL sites (`--mysql`)
- Reverse proxy sites (`--proxy host[:port]`)
- Alias/redirect-like vhosts (`--alias domain`)
- WordPress single site and multisite variants

This repository is the CLI source code, templates, install scripts, and tests.

## Current Scope (From Code)

- Runtime framework: Cement (`wo/cli/main.py`)
- Site state DB: SQLite via SQLAlchemy (`wo/core/database.py`, `wo/cli/plugins/models.py`)
- Site lifecycle: `wo/cli/plugins/site_*.py`
- Stack install/upgrade/remove: `wo/cli/plugins/stack*.py`
- Templates rendered by commands: `wo/cli/templates/*.mustache`
- Backup service: `wo/core/backup.py`

## Quick Command Examples

```bash
# Create non-WordPress sites
wo site create example.com --html
wo site create example.com --php --php84
wo site create example.com --mysql --php83
wo site create example.com --proxy 127.0.0.1:3000
wo site create alias.example.com --alias example.com

# Create WordPress sites
wo site create blog.example.com --wp
wo site create shop.example.com --wpfc
wo site create network.example.com --wpsubdir
wo site create network.example.com --wpsubdomain
wo site create app.example.com --wp --template docs/examples/wp-template.json

# Change site type / cache / PHP version
wo site update example.com --php82
wo site update example.com --wpredis
wo site update example.com --letsencrypt=on

# Backup / restore
wo site backup example.com
wo site backup --all --path /mnt/backups
wo site restore /var/www/example.com/backup/example.com/2026-01-10_03-20-11.tar.zst

# Site HTTP basic auth
wo site secure example.com
wo site secure example.com --rm

# Stack management
wo stack install --web
wo stack install --php84 --redis
wo stack upgrade --all
wo stack status

# WordPress autoupdate + visual regression
wo site autoupdate backstop app.example.com --urls /,/pricing,/contact --reference
wo site autoupdate run app.example.com

# WordOps self update (alias to wo_update controller)
wo update
```

## Non-WordPress Deployment Modes

WordOps can be used to deploy and operate non-WordPress sites directly:

- Static websites (`--html`)
- Custom PHP websites (`--php` + optional `--php74..--php84`)
- PHP + MySQL applications (`--mysql`)
- Reverse proxy vhosts (`--proxy host[:port]`)
- Redirect/alias vhosts (`--alias domain`)

Implementation details, lifecycle support, and caveats:
- `docs/SITE_TYPE_CAPABILITIES.md`

## WordPress Provisioning Templates

WordPress provisioning templates are supported during `wo site create`:

```bash
wo site create app.example.com --wp --template docs/examples/wp-template.json
```

Implemented behavior:
- Template file must be a valid JSON object.
- Top-level sections: `themes`, `plugins`, `options`, `constants`.
- Each theme/plugin entry must define `slug` or `url`.
- Optional booleans:
  - `activate` for activation
  - `network` for multisite network scope
- Plugin entry `options` are applied after install using WP-CLI option/meta updates.

Repository examples:
- `docs/examples/wp-template.json`
- `docs/examples/wp-kadence-template.json`

Full schema and execution details:
- `docs/WORDPRESS_TEMPLATE_USAGE.md`

## Visual Regression in Autoupdate (BackstopJS)

Autoupdate supports visual regression checks through BackstopJS hooks.

1. Scaffold Backstop config/hook:
```bash
wo site autoupdate backstop app.example.com --urls /,/pricing,/contact --reference
```
2. Run updates:
```bash
wo site autoupdate run app.example.com
```

Code behavior:
- If `conf/backstop.config.js` exists, autoupdate generates a pre-update reference.
- Post-update it executes `conf/autoupdate-visual-cmd`.
- The default hook template runs:
  - `npx backstop test --config=<config_path> --report=CI`
- On visual failure, autoupdate attempts rollback by restoring the created backup archive.

## Repository Layout

- `wo/cli/main.py`: app entry point, root check, Cement app wiring
- `wo/cli/controllers/base.py`: root controller and `--version`
- `wo/cli/plugins/`: command controllers and shared site logic
- `wo/cli/templates/`: mustache templates used to render configs/scripts
- `wo/core/`: low-level helpers (services, shell, files, SSL, DB, backup)
- `config/plugins.d/*.conf`: plugin enablement and module wiring
- `tests/`: CLI and helper tests
- `docs/`: operational/developer documentation

## Important Generated Paths

- Nginx vhosts:
  - `/etc/nginx/sites-available/<domain>`
  - `/etc/nginx/sites-enabled/<domain>`
- Site webroot:
  - `/var/www/<domain>/`
- Site log symlinks:
  - `/var/www/<domain>/logs/access.log`
  - `/var/www/<domain>/logs/error.log`
- HTTP auth per-site ACL:
  - `/etc/nginx/acl/<slug>/protected.conf`
  - `/etc/nginx/acl/<slug>/credentials`
- Per-site PHP-FPM isolation:
  - `/etc/php/<ver>/fpm/php-fpm-<slug>.conf`
  - `/etc/php/<ver>/fpm/pool.d/<slug>.conf`
  - `/run/php/php<verNoDot>-fpm-<slug>.sock`
  - `systemd: php<ver>-fpm@<slug>`

## Documentation Index

- Full command reference: `WORDOPS_COMMANDS_REFERENCE.md`
- Architecture + extension guide: `docs/ARCHITECTURE_AND_EXTENSION_GUIDE.md`
- Site-type capability matrix (static/php/mysql/proxy/alias/wp): `docs/SITE_TYPE_CAPABILITIES.md`
- WordPress template schema and examples: `docs/WORDPRESS_TEMPLATE_USAGE.md`
- Autoupdate behavior: `docs/AUTOUPDATE_USAGE.md`
- Backup internals: `docs/BACKUP_ARCHITECTURE.md`

## Notes

- The CLI expects root privileges (`wo/cli/main.py` enforces `geteuid() == 0`).
- The codebase includes legacy commands and compatibility paths; docs in this repo are aligned to what current code does, including known quirks.
