# Architecture And Extension Guide

This guide is based on current code behavior in this repository.

## 1. Runtime Architecture

### Entry point and app wiring

- Entry: `wo/cli/main.py`
- App class: `WOApp(CementApp)`
- Base controller: `wo/cli/controllers/base.py`

Bootstrapping details:
- `bootstrap = 'wo.cli.bootstrap'`
- `plugin_bootstrap = 'wo.cli.plugins'`
- `template_module = 'wo.cli.templates'`
- Extensions: `mustache`, `argcomplete`, `colorlog`
- Root privilege is enforced in `main()` (`geteuid() == 0`)

### Plugin loading model

Enabled plugins are configured in `/etc/wo/plugins.d/*.conf`.
This repo ships defaults under `config/plugins.d/`.

Each plugin file usually exposes:
- controller class(es)
- `load(app)` registering controllers and hooks

## 2. Persistence Model

### ORM + SQLite

- Engine/session: `wo/core/database.py`
- Model: `wo/cli/plugins/models.py` (`SiteDB` table `sites`)

`SiteDB` fields include:
- `sitename`
- `site_type`, `cache_type`
- `site_path`
- `is_enabled`, `is_ssl`
- `db_name`, `db_user`, `db_password`, `db_host`
- `php_version`
- storage flags and metadata fields

CRUD helpers are in `wo/cli/plugins/sitedb.py`.

## 3. Site Lifecycle (Actual Flow)

### Create (`wo site create`)

Main orchestrator:
- `wo/cli/plugins/site_create.py`

Core shared helper functions:
- `determine_site_type()`
- `setupdomain()`
- `setupdatabase()`
- `setupwordpress()`
- `setup_php_fpm()`
- `setup_letsencrypt_advanced()`

Source:
- `wo/cli/plugins/site_functions.py`

Create flow summary:
1. Parse site/cache/type options.
2. Validate domain and ensure no existing site/conf conflict.
3. Render nginx vhost (`virtualconf.mustache`) and webroot structure.
4. Insert site record in SQLite.
5. Optionally create DB + config (`wo-config.php` for mysql type).
6. Optionally install/configure WordPress and cache plugins.
7. Create isolated per-site PHP-FPM unit/pool/user.
8. Reload nginx and set ownership/permissions.
9. Optionally configure Let's Encrypt and redirects.

WordPress template path in create flow:
- CLI `--template` value is parsed in `site_create.py`.
- `load_wp_template()` validates and normalizes template JSON.
- `setupwordpress()` calls `apply_wp_template()` after core install/permalink/cache setup.
- Template support docs:
  - `docs/WORDPRESS_TEMPLATE_USAGE.md`

### Update (`wo site update`)

Orchestrator:
- `wo/cli/plugins/site_update.py`

Capabilities:
- site type transitions (`html/php/mysql/wp/...`)
- cache transitions (`basic/wpfc/wpsc/wpredis/wprocket/wpce`)
- PHP version switching (`php74`..`php84`)
- ssl/hsts/ngxblocker/password workflows
- bulk updates via `--all`

Important internals:
- uses `PHPVersionManager` from `site_functions.py`
- safe backup helpers exist (`safe_site_backup_for_update`, `rollback_site_from_backup`) but current main update path is still mixed with legacy flows

### Delete (`wo site delete`)

Defined in `wo/cli/plugins/site.py` (`WOSiteDeleteController`).

Deletes:
- nginx vhost + enabled symlink
- optional DB and/or webroot
- site record in SQLite
- ACME-related conf
- ACL directory (`/etc/nginx/acl/<slug>`)
- per-site PHP-FPM artifacts via `cleanup_php_fpm()` when `php_version` exists

### Clone (`wo site clone`)

Defined in `wo/cli/plugins/site_clone.py`.

Current constraints:
- source must be WordPress type

Clone steps include:
- create destination site infra
- clone DB + files
- regenerate destination `wp-config.php`
- update URLs in DB
- copy ACL files
- setup php-fpm and optional SSL when source is SSL

### Backup / Restore

- Manual backup command: `wo/cli/plugins/site_backup.py`
- Restore command: `wo/cli/plugins/site_restore.py`
- Central service: `wo/core/backup.py`

Backup service (`WOBackup`) supports:
- full
- db-only
- files-only

Restore consumes `vhost.json` metadata from archive and recreates site state.

Restore limitation:
- Proxy/alias restores are partial in current implementation because restore builds generic vhost context and does not fully reconstruct source proxy target details from metadata.

### Site basic auth

- Controller: `wo/cli/plugins/site_secure.py`
- Alias command under `site`: `secure`

Files used:
- `/etc/nginx/acl/<slug>/protected.conf`
- `/etc/nginx/acl/<slug>/credentials`

## 4. Supported Site Types and Cache Types

### Site types seen in code

- `html`
- `php`
- `mysql`
- `proxy`
- `alias`
- `wp`
- `wpsubdir`
- `wpsubdomain`
- `subsite` (creation/update helper flow)

Non-WordPress deployment intent:
- `html`: static files only (`htdocs`), no DB provisioning.
- `php`: custom PHP apps with per-site PHP-FPM socket.
- `mysql`: custom PHP + MariaDB helper flow (`wo-config.php` written in webroot).
- `proxy`: reverse proxy vhost to upstream host:port.
- `alias`: redirect vhost.

### Cache types seen in code

- `basic`
- `wpfc`
- `wpsc`
- `wpredis`
- `wprocket`
- `wpce`

Parser for type/cache combinations:
- `detSitePar()` in `site_functions.py`

Complete lifecycle matrix:
- `docs/SITE_TYPE_CAPABILITIES.md`

## 5. Per-Site PHP-FPM Isolation

Setup helper:
- `setup_php_fpm()` in `site_functions.py`

For a site slug `example-com` on PHP 8.4:
- user/group: `php-example-com`
- service template: `/etc/systemd/system/php8.4-fpm@.service`
- master conf: `/etc/php/8.4/fpm/php-fpm-example-com.conf`
- pool conf: `/etc/php/8.4/fpm/pool.d/example-com.conf`
- socket: `/run/php/php84-fpm-example-com.sock`

Cleanup helper:
- `cleanup_php_fpm()` removes old service/pool/log/socket artifacts and optionally user/group.

## 6. Nginx Configuration Layout

Code references these directories/files:
- `/etc/nginx/sites-available/`
- `/etc/nginx/sites-enabled/`
- `/etc/nginx/conf.d/`
- `/etc/nginx/common/`
- `/etc/nginx/acl/`  (singular in code)

Site webroot layout:
- `/var/www/<domain>/htdocs`
- `/var/www/<domain>/logs`
- `/var/www/<domain>/conf/nginx`

Templates are rendered from:
- `wo/cli/templates/*.mustache`

Key templates:
- `virtualconf.mustache`
- `php.mustache`
- `wp.mustache`
- `php-fpm-service.mustache`
- `php-fpm-master.mustache`
- `php-fpm-pool.mustache`
- `protected.mustache`
- `ssl.mustache`

## 7. Stack Management Architecture

Main stack controller:
- `wo/cli/plugins/stack.py`

Helper classes in same module:
- `PackageManager`
- `StackComponentInstaller`
- `StackRemover`

Related modules:
- `stack_pref.py` (post-install config rendering and system tuning)
- `stack_upgrade.py`
- `stack_migrate.py`
- `stack_services.py`

Component/version constants live in:
- `wo/core/variables.py`

## 8. Autoupdate Architecture

Controller:
- `wo/cli/plugins/site_autoupdate.py`

Commands:
- `run`
- `schedule`
- `backstop`

Core behavior:
- WordPress-only target filtering
- lock files to avoid concurrent runs
- checks core/plugin/theme updates via WP eval script
- always creates a backup before applying updates
- optional visual regression command hook
- rollback on update/visual failure via `wo site restore <archive>`

WP-CLI execution model:
- Autoupdate runs WP-CLI as the site's per-site PHP-FPM user (`php-<slug>`) via uid/gid demotion.
- Requires root context and POSIX user APIs.
- Uses dedicated per-site temporary HOME/cache paths under `/tmp/wp-cli-<slug>/`.

Visual regression model:
- `backstop` subcommand scaffolds:
  - `conf/backstop.config.js` from `backstop.config.js.mustache`
  - `conf/autoupdate-visual-cmd` from `autoupdate-visual-cmd.mustache`
- On each autoupdate run (if config exists):
  1. generate fresh baseline reference (`npx backstop reference`)
  2. apply WP updates
  3. execute visual hook command (`autoupdate-visual-cmd`)
  4. if hook returns non-zero, rollback from created backup archive
- Old Backstop test bitmap directories are pruned (keep latest 5).

Generated logs:
- `/var/log/wo/autoupdate/<slug>/...`
- run summaries in `/var/log/wo/autoupdate/run-<timestamp>.json`

## 9. Key Core Utilities

- Shell wrapper: `wo/core/shellexec.py` (`WOShellExec`)
- Service operations: `wo/core/services.py` (`WOService`)
- File helpers: `wo/core/fileutils.py` (`WOFileUtils`)
- SSL helpers: `wo/core/sslutils.py`
- ACME integration: `wo/core/acme.py`
- MySQL helpers: `wo/core/mysql.py`
- Template deploy: `wo/core/template.py`
- Downloads: `wo/core/download.py`

## 10. How To Extend (Recommended Pattern)

### Add a new CLI feature

1. Create a plugin controller in `wo/cli/plugins/<feature>.py`.
2. Register controller(s) in `load(app)`.
3. Add plugin config under `config/plugins.d/<feature>.conf`.
4. If persistent state is needed, extend `SiteDB` (or add a new model) and migration strategy.
5. Add tests in `tests/cli/`.

### Add a new site template capability

1. Add mustache file in `wo/cli/templates/`.
2. Pass required render data from site orchestration helper/controller.
3. Update `virtualconf.mustache` or include chain as needed.
4. Add tests validating rendered output and behavior.

### Add a new PHP version

Current version mapping is centralized in:
- `WOVar.wo_php_versions`
- `PHPVersionManager.SUPPORTED_VERSIONS`

Update both mapping points plus apt package definitions in `wo/core/variables.py`.

## 11. Known Quirks (Code Reality)

- ACL path in code is `/etc/nginx/acl/` (not `acls/`).
- `debug` plugin still has legacy PHP 7.2/7.3 debug-specific flows.
- `wo site autoupdate schedule` parses enable/disable flags from raw argv instead of declared Cement arguments.
- Some docs/manpage history still reference old command names and old php versions; use this guide and command reference as authoritative for current repo state.
- `wo site update --html` exists but is not a robust conversion path in normal update flow.

## 12. Testing Workflow

Baseline:
- `pytest -q`

Targeted examples:
- `pytest tests/cli/18_test_site_create.py -q`
- `pytest tests/cli/24_test_site_update.py -q`
- `pytest tests/cli/28_test_secure.py -q`
- `pytest tests/cli/32_test_site_backup.py -q`

When editing templates, also validate nginx syntax in real environments:
- `nginx -t`
