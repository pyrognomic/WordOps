# AGENTS

## General guidelines
- Use `rg` for code searches instead of `grep -R` or `ls -R`.
- Keep patches focused and commit with descriptive messages.
- Run `pytest -q` and any relevant test modules before committing changes.
- Ensure `git status` is clean after every commit.

## Codebase overview
WordOps is a Python CLI built on top of the `cement` framework. Important
locations and components:

- `wo/cli/main.py` – defines `WOApp` and wires all controllers together.
- `wo/cli/controllers/base.py` – `WOBaseController` with common arguments.
- `wo/cli/plugins/` – individual command groups. Each module exposes a
  `WO…Controller` class extending `CementBaseController`.
  - `site_create.py`, `site_update.py`, `site_clone.py` – manage vhost life cycle.
  - `secure.py` – `WOSecureController` toggles HTTP basic authentication by
    patching vhost files.
  - `stack_*` modules – install or upgrade server-wide components.
- `wo/cli/plugins/site_functions.py` – shared helpers. Notable functions:
  - `setup_php_fpm()` – render systemd units and pool configs for per-site
    PHP-FPM services.
  - `cleanup_php_fpm()` – remove legacy PHP-FPM pools when switching versions.
- `wo/cli/templates/` – mustache templates used to render Nginx, PHP-FPM and
  other configuration files.

## Nginx configuration notes
WordOps stores generated Nginx files under `/etc/nginx` using a mix of per-site
variables and shared includes:

- `common/` – reusable snippets such as `php.conf`, `wp.conf`, and `redis.conf`
- `conf.d/` – global tuning, maps, and other server-wide snippets
- `acls/` – per-site `htpasswd` files and security includes
- `sites-available/` – full vhost definitions
- `sites-enabled/` – symlinks to enabled vhosts

### Directory structure

```
/etc/nginx
├── nginx.conf                 # top-level config includes conf.d/ and sites-enabled/
├── fastcgi.conf
├── fastcgi_params
├── proxy_params
├── acls/                      # per-site auth files rendered by `wo secure`
│   ├── htpasswd-<slug>
│   └── secure-<slug>.conf
├── common/                    # reusable WordOps snippets
│   ├── php.conf               # generic PHP handler
│   ├── wp.conf                # WordPress rewrites and ACL hooks
│   ├── redis.conf             # Redis cache integration
│   └── ...                    # other specific configs
├── conf.d/                    # global Nginx tuning and maps
│   ├── gzip.conf
│   ├── map-wp-fastcgi-cache.conf
│   └── ...
├── sites-available/           # full vhost files
│   └── <domain>
├── sites-enabled/             # symlinks to enabled vhosts
│   └── <domain> -> ../sites-available/<domain>
└── snippets/                  # drop-in configs like fastcgi-php.conf
```

Each vhost sets its PHP-FPM context and pulls in the generic handler:

```
set $php_ver   <version>;   # e.g. 84 for PHP 8.4
set $pool_name <slug>;      # site slug for the PHP-FPM pool
include common/php.conf;    # -> /run/php/php${php_ver}-fpm-${pool_name}.sock
```

WordPress sites include `common/wp.conf` for WordPress-specific routing and login
protection.
## PHP-FPM isolation
Each site runs its own PHP-FPM master process and pool. `setup_php_fpm()`
creates the systemd unit, master config, pool file, log directory and user
for a given `pool_name` and `php_ver`. Nginx snippets such as
`common/php.conf` and `common/wp.conf` connect to the socket
`/run/php/php${php_ver}-fpm-${pool_name}.sock`.

When a site changes PHP versions, `cleanup_php_fpm()` removes the obsolete
service template, pool config, log files and sockets for the previous version.

### How vhosts, services and users fit together
For a domain such as `example.com` WordOps derives a slug (`example-com`) and
creates a dedicated Unix user `php-example-com`. `setup_php_fpm()` then
generates:

- `/etc/systemd/system/php<ver>-fpm@.service` – templated unit used to spawn a
  master process for each pool
- `/etc/php/<ver>/fpm/php-fpm-<slug>.conf` – master FPM config loaded by the
  unit
- `/etc/php/<ver>/fpm/pool.d/<slug>.conf` – pool definition run as the site’s
  user and writing logs to `/var/log/php/<ver>/<slug>/`

The vhost sets `$php_ver` and `$pool_name` (the slug) and includes
`common/php.conf`, which points Nginx to
`/run/php/php${php_ver}-fpm-${pool_name}.sock`.

### Template reference
Key templates in `wo/cli/templates/`:

- `php-fpm-service.mustache` – systemd unit shown above
- `php-fpm-master.mustache` – writes `php-fpm-<slug>.conf`
- `php-fpm-pool.mustache` – defines the pool and user permissions
- `php.mustache` – server snippet that sets `$php_ver`/`$pool_name`
- `wp.mustache` – WordPress routing and login protection
- `redis.mustache` – optional Redis caching snippet
- `virtualconf.mustache` – base Nginx vhost pulling the snippets together

## Extending functionality
- New CLI features live under `wo/cli/plugins/`; register controllers in
  `wo/cli/main.py`.
- Store templates in `wo/cli/templates/` and render them through helpers in
  `site_functions.py`.
- Generated examples under `etc-adjusted/` illustrate the final layout in
  `/etc/nginx` and can serve as references when editing templates.

## Testing and style
- Run `pytest -q` plus targeted modules like `pytest tests/cli/28_test_secure.py -q`
  when touching related code.
- Maintain two-space indentation in templates and avoid trailing whitespace.
- For Nginx changes, `nginx -t` can help validate syntax if available.