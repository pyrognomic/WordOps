# WordOps Commands Reference (Code-Accurate)

This reference is generated from the current Python controllers in `wo/cli/plugins/`.

## Top-Level Commands

- `wo clean`
- `wo debug`
- `wo import_slow_log` (deprecated shim)
- `wo info`
- `wo log`
- `wo maintenance`
- `wo secure`
- `wo site`
- `wo stack`
- `wo sync`
- `wo update` (alias for controller label `wo_update`)

## Global

- `wo --version`

## `wo site`

### Base site operations

- `wo site enable <domain>`
- `wo site disable <domain>`
- `wo site info <domain>`
- `wo site log <domain>`
- `wo site show <domain>`
- `wo site cd <domain>`
- `wo site list [--enabled|--disabled]`
- `wo site edit <domain>`
- `wo site delete <domain> [--db] [--files] [--all] [--force] [--no-prompt]`

### `wo site create`

Usage:
- `wo site create <domain> [options]`

Site-type options:
- `--html`
- `--php`
- `--mysql`
- `--wp`
- `--wpsubdir`
- `--wpsubdomain`
- `--wpfc`
- `--wpsc`
- `--wprocket`
- `--wpce`
- `--wpredis`
- `--proxy <host[:port]>`
- `--alias <domain>`
- `--subsiteof <multisite-domain>`

PHP version selectors:
- `--php74`
- `--php80`
- `--php81`
- `--php82`
- `--php83`
- `--php84`

WordPress options:
- `--user <wp_admin_user>`
- `--email <wp_admin_email>`
- `--pass <wp_admin_password>`
- `--vhostonly`
- `--template <FILE>` (WordPress template JSON)

SSL/options:
- `-le, --letsencrypt [on|subdomain|wildcard]`
- `--force` (for cert issuance checks)
- `--dns [provider]` (defaults to `dns_cf` behavior when no explicit provider value)
- `--dnsalias <domain>`
- `--hsts`
- `--ngxblocker`

Site security option at create time:
- `--secure` (creates HTTP basic auth credentials)

Notes from code:
- If no type flags are provided, site defaults to `html` (`detSitePar`/`determine_site_type`).
- `--proxy`, `--alias`, and `--subsiteof` are mutually exclusive with other site type switches.
- For custom app deployment:
  - `--html`: static files in `<webroot>/htdocs`
  - `--php`: PHP app in `<webroot>/htdocs` using per-site PHP-FPM socket
  - `--mysql`: same as `--php` plus DB/user provisioning and `wo-config.php`

WordPress template provisioning:
- Use `--template <FILE>` with WordPress site types.
- Template loading/validation is implemented in `load_wp_template()`.
- Template application is implemented in `apply_wp_template()` and runs after WordPress core install.
- Schema details and examples:
  - `docs/WORDPRESS_TEMPLATE_USAGE.md`
  - `docs/examples/wp-template.json`
  - `docs/examples/wp-kadence-template.json`

### `wo site update`

Usage:
- `wo site update <domain> [options]`
- `wo site update --all [options]`

Type/cache options:
- `--html`
- `--php`
- `--mysql`
- `--wp`
- `--wpsubdir`
- `--wpsubdomain`
- `--wpfc`
- `--wpsc`
- `--wprocket`
- `--wpce`
- `--wpredis`
- `--proxy <host[:port]>`
- `--alias <domain>`
- `--subsiteof <multisite-domain>`

PHP selectors:
- `--php74`
- `--php80`
- `--php81`
- `--php82`
- `--php83`
- `--php84`

WordPress/site options:
- `--password` (updates WP user password workflow)

SSL/options:
- `-le, --letsencrypt [on|off|renew|subdomain|wildcard|clean|purge]`
- `--force`
- `--dns [provider]`
- `--dnsalias <domain>`
- `--hsts [on|off]`
- `--ngxblocker [on|off]`

Bulk mode:
- `--all`

Notes from code:
- `--all` cannot be combined with explicit `site_name`.
- Some actions (`--password`, `--hsts`, `--ngxblocker`, `--letsencrypt=renew`) run without requiring a type transition.

### `wo site clone`

Usage:
- `wo site clone <source_domain> <dest_domain> [--user] [--email] [--pass]`

Code behavior:
- Only WordPress source sites are allowed.
- Clones DB + files + ACL + per-site PHP-FPM and updates URLs.

### `wo site backup`

Usage:
- `wo site backup <domain> [--db] [--files] [--path <dir>]`
- `wo site backup --all [--db] [--files] [--path <dir>]`

### `wo site restore`

Usage:
- `wo site restore <backup_archive_or_extracted_directory>`

Code behavior:
- Reads `vhost.json` from backup and recreates site, vhost, DB metadata, ACL, PHP-FPM, and files.
- Proxy/alias restore is partial; source proxy host/port or alias target are not fully preserved in backup metadata used by restore.

### `wo site secure` (alias `wo site site-secure`)

Usage:
- `wo site secure <domain> [<username> <password>]`
- `wo site secure <domain> --rm`

Code behavior:
- Writes `/etc/nginx/acl/<slug>/credentials` with Apache MD5 hash via `openssl passwd -apr1`.
- Renders `protected.mustache` for enable/disable and reloads nginx.

### `wo site autoupdate`

Subcommands:
- `wo site autoupdate run [<domain>|--all] [--dry-run] [--no-visual] [--backup-dir <dir>]`
- `wo site autoupdate schedule --enable|--disable [--interval=hourly|daily]`
- `wo site autoupdate backstop [<domain>|--all] [--urls <csv>] [--urls-file <file>] [--reference] [--approve]`

Important code-accurate notes:
- No `--backup-only` flag exists in current controller.
- `schedule` parses `--enable/--disable/--interval` from raw argv.
- Updates are WordPress-only (`'wp' in site_type`).
- Flow is: detect updates -> backup -> update -> visual test -> rollback on failure.

## Site Type Capability Matrix

Legend:
- `Yes`: implemented and intended
- `Partial`: implemented with limitations
- `No`: blocked by current controller logic

| Site type | Create | Update | Backup | Restore | Clone | Autoupdate |
|---|---|---|---|---|---|---|
| `html` | Yes | Partial | Yes | Yes | No | No |
| `php` | Yes | Yes | Yes | Yes | No | No |
| `mysql` | Yes | Yes | Yes | Yes | No | No |
| `proxy` | Yes | Yes | Yes | Partial | No | No |
| `alias` | Yes | Yes | Yes | Partial | No | No |
| `wp`/`wpsubdir`/`wpsubdomain` | Yes | Yes | Yes | Yes | Yes | Yes |

Notes:
- `wo site clone` only allows WordPress sources.
- `wo site autoupdate` only processes WordPress sites.
- `wo site update --html` exists as a switch, but does not provide a reliable type-conversion path in normal update flow.

Deep dive:
- `docs/SITE_TYPE_CAPABILITIES.md`

Visual regression details:
- Scaffold Backstop config/hook:
  - `wo site autoupdate backstop <site> --urls /,/about --reference`
- Backstop scaffold writes:
  - `<site_path>/conf/backstop.config.js`
  - `<site_path>/conf/autoupdate-visual-cmd`
- During `run`, if backstop config exists, code generates a pre-update reference first.
- Visual step executes hook command from `autoupdate-visual-cmd`.
- Default hook template command:
  - `npx backstop test --config={{config_path}} --report=CI`
- If visual step fails, restore is attempted from the backup archive created for the run.

## `wo stack`

Subcommands exposed by controllers:
- `wo stack install [options]`
- `wo stack remove [options]`
- `wo stack purge [options]`
- `wo stack upgrade [options]`
- `wo stack migrate [options]`
- `wo stack start [options]`
- `wo stack stop [options]`
- `wo stack restart [options]`
- `wo stack reload [options]`
- `wo stack status [options]`

### Common stack flags

Group flags:
- `--all`
- `--web`
- `--admin`
- `--security`

Component flags:
- `--nginx`
- `--php`
- `--mysql`
- `--mariadb` (alias semantics)
- `--mysqlclient`
- `--mysqltuner`
- `--wpcli`
- `--phpmyadmin`
- `--phpredisadmin`
- `--composer`
- `--netdata`
- `--dashboard`
- `--extplorer`
- `--adminer`
- `--fail2ban`
- `--clamav`
- `--ufw`
- `--sendmail`
- `--utils`
- `--redis`
- `--proftpd`
- `--ngxblocker`
- `--cheat`
- `--nanorc`
- `--brotli` (handled specially)
- `--force`

PHP version flags:
- `--php74`
- `--php80`
- `--php81`
- `--php82`
- `--php83`
- `--php84`

Upgrade-specific extras (`wo stack upgrade`):
- `--no-prompt`

Migrate-specific flags (`wo stack migrate`):
- `--mariadb`
- `--nginx`
- `--force`
- `--ci` (test/internal path)

## `wo log`

Subcommands:
- `wo log show [site_name] [--nginx] [--php] [--fpm] [--mysql] [--wp] [--access] [--all]`
- `wo log reset [site_name] [--nginx] [--php] [--fpm] [--mysql] [--wp] [--access] [--all] [--slow-log-db]`
- `wo log gzip [site_name] [--nginx] [--php] [--fpm] [--mysql] [--wp] [--access] [--all]`
- `wo log mail [site_name] [same selectors] --to <email> [--to <email> ...]`

## `wo info`

Usage:
- `wo info [--nginx] [--php] [--mysql] [--php74|--php80|--php81|--php82|--php83|--php84]`

Default behavior in code:
- If no explicit selector is set, prints nginx + php + mysql information.

## `wo clean`

Usage:
- `wo clean [--fastcgi] [--opcache] [--redis] [--all]`

Default behavior:
- With no flags, only fastcgi cache is cleaned.

## `wo maintenance`

Usage:
- `wo maintenance`

Behavior:
- Runs apt update + dist-upgrade + autoremove/autoclean.

## `wo secure`

Controller provides SSH hardening command:
- `wo secure ssh [--hostname <name>] [--user <name>] [--port <port>] [--allow-password] [--force]`

Behavior highlights:
- Sets hostname
- Creates/provisions admin user
- Writes sshd hardening drop-in (`/etc/ssh/sshd_config.d/00-hardening.conf`)
- Restarts SSH service

## `wo debug`

Usage pattern:
- `wo debug [site_name] [--nginx on|off] [--php on|off] [--fpm on|off] [--mysql on|off] [--wp on|off] [--rewrite on|off] [--all on|off] [--import-slow-log] [--import-slow-log-interval N] [-i|--interactive]`

Notes from code:
- Debug paths still include legacy PHP 7.2/7.3 specific flows.
- Also supports importing slow log into Anemometer data schema.

## `wo import_slow_log`

- Deprecated command. Controller prints migration hint to `wo debug --import-slow-log`.

## `wo sync`

Usage:
- `wo sync`

Behavior:
- Reconciles site DB credentials in WordOps SQLite database by parsing `*-config.php` / `wp-config.php`.

## `wo update`

Alias-backed command for `wo_update` controller.

Usage:
- `wo update [--force] [--beta] [--mainline] [--branch [BRANCH]] [--travis]`

Behavior:
- Checks latest GitHub release and executes update install script.

## Data and Config Paths

- Main config: `/etc/wo/wo.conf`
- Plugin configs: `/etc/wo/plugins.d/*.conf`
- WordOps DB URI source: `WOVar.wo_db_uri` (default resolves to `/var/lib/wo/dbase.db`)
- WordOps log: `/var/log/wo/wordops.log`

## WordPress Template Schema (Implemented)

Used with:
- `wo site create <domain> --wp --template <FILE>`

Top-level JSON keys:
- `themes`: array
- `plugins`: array
- `options`: object
- `constants`: object

Theme/plugin entry requirements:
- must define at least `slug` or `url`
- optional `activate` (boolean)
- optional `network` (boolean)

Plugin entry additional key:
- `options` (object), applied after plugin install

Application order in code:
1. themes
2. plugins (and plugin options)
3. global `options`
4. global `constants`

Reference:
- `docs/WORDPRESS_TEMPLATE_USAGE.md`

## Known Implementation Quirks Worth Knowing

- The ACL directory used by code is `/etc/nginx/acl/` (singular), not `acls/`.
- Some legacy plugins (`debug`, parts of manpage history) still reference old php7.2/php7.3 debug pools.
- `wo site autoupdate schedule` interprets enable/disable flags from raw argv parsing, not controller argument declarations.
- `wo site clone` explicitly blocks non-WordPress sources.
