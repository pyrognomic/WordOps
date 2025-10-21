# WordOps Commands Reference

Complete reference for all WordOps CLI commands, subcommands, and arguments.

## Table of Contents

- [WordOps Commands Reference](#wordops-commands-reference)
  - [Table of Contents](#table-of-contents)
  - [Clean](#clean)
    - [Subcommands](#subcommands)
      - [Clean FastCGI Cache](#clean-fastcgi-cache)
  - [Debug](#debug)
    - [Subcommands](#subcommands-1)
      - [Enable Debug](#enable-debug)
  - [Import Slow Log](#import-slow-log)
  - [Info](#info)
    - [Subcommands](#subcommands-2)
      - [Show Configuration](#show-configuration)
  - [Log](#log)
    - [Subcommands](#subcommands-3)
      - [Show Logs](#show-logs)
      - [Reset Logs](#reset-logs)
      - [GZip Logs](#gzip-logs)
  - [Maintenance](#maintenance)
    - [Subcommands](#subcommands-4)
      - [Enable Maintenance](#enable-maintenance)
  - [Secure SSH](#secure-ssh)
    - [Subcommands](#subcommands-5)
      - [Secure SSH](#secure-ssh-1)
  - [Site](#site)
    - [Subcommands](#subcommands-6)
    - [Site Create](#site-create)
    - [Site Update](#site-update)
    - [Site Delete](#site-delete)
    - [Site Show](#site-show)
    - [Site Edit](#site-edit)
    - [Site List](#site-list)
    - [Site Autoupdate](#site-autoupdate)
    - [Site Backup](#site-backup)
    - [Site Clone](#site-clone)
    - [Site Restore](#site-restore)
    - [Site Secure](#site-secure)
  - [Stack](#stack)
    - [Subcommands](#subcommands-7)
    - [Stack Install](#stack-install)
    - [Stack Remove](#stack-remove)
    - [Stack Purge](#stack-purge)
    - [Stack Migrate](#stack-migrate)
    - [Stack Upgrade](#stack-upgrade)
    - [Stack Services](#stack-services)
      - [Start Services](#start-services)
      - [Stop Services](#stop-services)
      - [Restart Services](#restart-services)
      - [Reload Services](#reload-services)
      - [Status Services](#status-services)
  - [Sync](#sync)
  - [Update](#update)
  - [Common Patterns](#common-patterns)
    - [Default Behavior](#default-behavior)
    - [PHP Version Handling](#php-version-handling)
    - [SSL Certificate Options](#ssl-certificate-options)
    - [Cache Types](#cache-types)
    - [Cache Transitions](#cache-transitions)
  - [File Locations](#file-locations)
    - [Site Files](#site-files)
    - [Configuration Files](#configuration-files)
    - [Backend Access](#backend-access)
  - [Architecture Details](#architecture-details)
    - [Per-Site User Isolation](#per-site-user-isolation)
    - [PHP Version Changes](#php-version-changes)
    - [Visual Regression Testing (Autoupdate)](#visual-regression-testing-autoupdate)
  - [Notes](#notes)
  - [Related Files](#related-files)

---

## Clean

**Command:** `wo clean`

**Description:** Clean NGINX FastCGI cache, Redis cache, opcache, and various logs.

### Subcommands

#### Clean FastCGI Cache

**Usage:** `wo clean [sitename] [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional | Domain name to clean cache for |
| `--fastcgi` | Flag | Clean NGINX FastCGI cache |
| `--redis` | Flag | Clean Redis cache |
| `--opcache` | Flag | Clean PHP opcache |
| `--all` | Flag | Clean all caches |

---

## Debug

**Command:** `wo debug`

**Description:** Enable or disable debugging for a site.

### Subcommands

#### Enable Debug

**Usage:** `wo debug [sitename] [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to debug |
| `--nginx` | Flag | Enable Nginx debugging (logs) |
| `--php` | Flag | Enable PHP debugging |
| `--mysql` | Flag | Enable MySQL slow query logging |
| `--wp` | Flag | Enable WordPress debugging |
| `--rewrite` | Flag | Enable rewrite debugging |
| `--all` | Flag | Enable all debugging options |
| `-i`, `--interactive` | Flag | Interactive debug mode |
| `--start` | Flag | Start debugging |
| `--stop` | Flag | Stop debugging |
| `--import-slow-log` | Flag | Import MySQL slow log to Anemometer |

**Default Behavior:** If no flags specified, enables all debugging options.

---

## Import Slow Log

**Command:** `wo import-slow-log`

**Description:** Import MySQL slow log to Anemometer database for analysis.

**Usage:** `wo import-slow-log`

**Note:** This is typically used internally by the debug command.

---

## Info

**Command:** `wo info`

**Description:** Display configuration information about NGINX, PHP, and MySQL.

### Subcommands

#### Show Configuration

**Usage:** `wo info [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--nginx` | Flag | Show NGINX configuration |
| `--php` | Flag | Show PHP configuration |
| `--mysql` | Flag | Show MySQL configuration |

**Default Behavior:** If no flags specified, shows all configuration information.

---

## Log

**Command:** `wo log`

**Description:** Perform various log related operations including viewing, resetting, and managing logs.

### Subcommands

#### Show Logs

**Usage:** `wo log show [sitename] [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional | Domain name to show logs for |
| `--nginx` | Flag | Show NGINX access and error logs |
| `--php` | Flag | Show PHP logs |
| `--mysql` | Flag | Show MySQL logs |
| `--wp` | Flag | Show WordPress debug log |
| `--access` | Flag | Show access logs only |
| `--error` | Flag | Show error logs only |

#### Reset Logs

**Usage:** `wo log reset [sitename] [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional | Domain name to reset logs for |
| `--nginx` | Flag | Reset NGINX logs |
| `--php` | Flag | Reset PHP logs |
| `--mysql` | Flag | Reset MySQL logs |
| `--wp` | Flag | Reset WordPress debug log |
| `--all` | Flag | Reset all logs |

#### GZip Logs

**Usage:** `wo log gzip [sitename] [options]`

Compress old log files.

---

## Maintenance

**Command:** `wo maintenance`

**Description:** Enable or disable maintenance mode for sites.

### Subcommands

#### Enable Maintenance

**Usage:** `wo maintenance [sitename] --on`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to enable maintenance mode |
| `--on` | Flag | Enable maintenance mode |
| `--off` | Flag | Disable maintenance mode |

---

## Secure SSH

**Command:** `wo secure`

**Description:** Secure SSH configuration by changing port, disabling password authentication, and configuring fail2ban.

### Subcommands

#### Secure SSH

**Usage:** `wo secure --ssh [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--ssh` | Flag | Secure SSH configuration |
| `--port` | Value | Custom SSH port (default: 22222) |
| `--whitelist` | Value | Whitelist IP addresses |

---

## Site

**Command:** `wo site`

**Description:** Perform site specific operations including create, update, delete, list, and more.

### Subcommands

### Site Create

**Usage:** `wo site create <sitename> [options]`

**Description:** Create a new website with various configurations.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name for the site |
| `--html` | Flag | Create basic HTML site |
| `--php` | Flag | Create PHP site |
| `--php74` | Flag | Create PHP 7.4 site |
| `--php80` | Flag | Create PHP 8.0 site |
| `--php81` | Flag | Create PHP 8.1 site |
| `--php82` | Flag | Create PHP 8.2 site |
| `--php83` | Flag | Create PHP 8.3 site |
| `--php84` | Flag | Create PHP 8.4 site |
| `--mysql` | Flag | Create MySQL database |
| `--wp` | Flag | Install WordPress |
| `--wpfc` | Flag | Install WordPress with FastCGI cache |
| `--wpsc` | Flag | Install WordPress with wp-super-cache |
| `--wpce` | Flag | Install WordPress with Cache Enabler |
| `--wprocket` | Flag | Install WordPress with WP-Rocket |
| `--wpredis` | Flag | Install WordPress with Redis cache |
| `--wpsubdir` | Flag | Install WordPress multisite with subdirectory |
| `--wpsubdomain` | Flag | Install WordPress multisite with subdomain |
| `--user` | Value | WordPress admin username |
| `--email` | Value | WordPress admin email |
| `--pass` | Value | WordPress admin password |
| `--letsencrypt` | Flag | Configure Let's Encrypt SSL |
| `--letsencrypt=wildcard` | Value | Configure wildcard SSL certificate |
| `--dns` | Value | DNS API for wildcard certificates |
| `--hsts` | Flag | Enable HSTS (HTTP Strict Transport Security) |
| `--ngxblocker` | Flag | Enable Nginx Ultimate Bad Bot Blocker |
| `--proxy` | Value | Setup reverse proxy for backend application |
| `--vhostonly` | Flag | Create vhost configuration only |
| `--skip-install` | Flag | Skip WordPress installation |
| `--skip-status` | Flag | Skip site status check |

**Site Types:**

- **HTML:** `--html`
- **PHP:** `--php` (default PHP 8.4)
- **PHP with specific version:** `--php74`, `--php80`, `--php81`, `--php82`, `--php83`, `--php84`
- **MySQL:** `--mysql`
- **WordPress:** `--wp`, `--wpfc`, `--wpsc`, `--wpce`, `--wprocket`, `--wpredis`
- **WordPress Multisite:** `--wpsubdir`, `--wpsubdomain`

**Examples:**

```bash
# Create basic HTML site
wo site create example.com --html

# Create WordPress site with FastCGI cache
wo site create example.com --wpfc

# Create WordPress with Redis and Let's Encrypt
wo site create example.com --wpredis --letsencrypt

# Create WordPress with specific PHP version
wo site create example.com --wp --php82

# Create WordPress multisite with subdomain
wo site create example.com --wpsubdomain --letsencrypt
```

---

### Site Update

**Usage:** `wo site update <sitename> [options]`

**Description:** Update site configuration, cache type, SSL, or PHP version.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to update |
| `--html` | Flag | Update to HTML site |
| `--php` | Flag | Update to PHP site |
| `--php74` | Flag | Update to PHP 7.4 |
| `--php80` | Flag | Update to PHP 8.0 |
| `--php81` | Flag | Update to PHP 8.1 |
| `--php82` | Flag | Update to PHP 8.2 |
| `--php83` | Flag | Update to PHP 8.3 |
| `--php84` | Flag | Update to PHP 8.4 |
| `--mysql` | Flag | Add MySQL database |
| `--wp` | Flag | Update to WordPress (or remove cache if already WordPress) |
| `--wpfc` | Flag | Update to WordPress with FastCGI cache |
| `--wpsc` | Flag | Update to WordPress with wp-super-cache |
| `--wpce` | Flag | Update to WordPress with Cache Enabler |
| `--wprocket` | Flag | Update to WordPress with WP-Rocket |
| `--wpredis` | Flag | Update to WordPress with Redis cache |
| `--wpsubdir` | Flag | Update to WordPress multisite subdirectory |
| `--wpsubdomain` | Flag | Update to WordPress multisite subdomain |
| `--letsencrypt` | Flag/Value | Add/renew Let's Encrypt SSL |
| `--letsencrypt=on` | Value | Add Let's Encrypt SSL |
| `--letsencrypt=renew` | Value | Renew Let's Encrypt SSL |
| `--letsencrypt=off` | Value | Remove Let's Encrypt SSL |
| `--letsencrypt=wildcard` | Value | Add wildcard SSL certificate |
| `--dns` | Value | DNS API for wildcard certificates |
| `--hsts` | Flag/Value | Enable/disable HSTS |
| `--hsts=on` | Value | Enable HSTS |
| `--hsts=off` | Value | Disable HSTS |
| `--ngxblocker` | Flag/Value | Enable/disable Nginx Bad Bot Blocker |
| `--ngxblocker=on` | Value | Enable Bad Bot Blocker |
| `--ngxblocker=off` | Value | Disable Bad Bot Blocker |
| `--proxy` | Value | Update reverse proxy configuration |
| `--password` | Flag | Change WordPress admin password |
| `--all` | Flag | Update all sites with specified options |
| `--force` | Flag | Force SSL certificate renewal |

**Examples:**

```bash
# Update PHP version
wo site update example.com --php83

# Add Let's Encrypt SSL
wo site update example.com --letsencrypt

# Change cache type from FastCGI to Redis
wo site update example.com --wpredis

# Remove cache (go back to basic WordPress)
wo site update example.com --wp

# Add wildcard SSL certificate
wo site update example.com --letsencrypt=wildcard --dns=dns_cf

# Update all sites to PHP 8.4
wo site update --all --php84

# Change WordPress admin password
wo site update example.com --password
```

---

### Site Delete

**Usage:** `wo site delete <sitename> [options]`

**Description:** Delete a website and optionally its database and files.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to delete |
| `--no-prompt` | Flag | Delete without confirmation |
| `--files` | Flag | Delete site files |
| `--db` | Flag | Delete database |
| `--all` | Flag | Delete everything (files + database) |
| `--force` | Flag | Force deletion without backup |

**Examples:**

```bash
# Delete site (keeps files and database)
wo site delete example.com

# Delete site with all files and database
wo site delete example.com --all

# Delete without confirmation
wo site delete example.com --no-prompt --all
```

---

### Site Show

**Usage:** `wo site show <sitename>`

**Description:** Display site information including configuration and credentials.

**Examples:**

```bash
wo site show example.com
```

---

### Site Edit

**Usage:** `wo site edit <sitename> [options]`

**Description:** Edit site configuration files.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name |
| `--nginx` | Flag | Edit Nginx vhost configuration |
| `--wpconfig` | Flag | Edit wp-config.php |
| `--php` | Flag | Edit PHP-FPM pool configuration |

**Examples:**

```bash
# Edit Nginx configuration
wo site edit example.com --nginx

# Edit WordPress configuration
wo site edit example.com --wpconfig
```

---

### Site List

**Usage:** `wo site list [options]`

**Description:** List all sites with optional filtering.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--enabled` | Flag | List enabled sites only |
| `--disabled` | Flag | List disabled sites only |

**Examples:**

```bash
# List all sites
wo site list

# List enabled sites only
wo site list --enabled
```

---

### Site Autoupdate

**Usage:** `wo site autoupdate <sitename> [options]`

**Description:** Enable or disable automatic WordPress core and plugin updates with visual regression testing using BackstopJS.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name |
| `--on` | Flag | Enable autoupdate |
| `--off` | Flag | Disable autoupdate |
| `--force` | Flag | Force autoupdate check now |

**How It Works:**
1. Before applying updates, takes visual screenshots of key pages
2. Applies WordPress and plugin updates
3. Takes new screenshots and compares with baseline
4. If differences detected, reports them
5. Cleans up old screenshot data after successful updates

**Examples:**

```bash
# Enable autoupdate
wo site autoupdate example.com --on

# Disable autoupdate
wo site autoupdate example.com --off

# Force autoupdate check immediately
wo site autoupdate example.com --force
```

---

### Site Backup

**Usage:** `wo site backup <sitename> [options]`

**Description:** Create backup of site files and database.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to backup |
| `--files` | Flag | Backup files only |
| `--db` | Flag | Backup database only |
| `--all` | Flag | Backup files and database (default) |

**Examples:**

```bash
# Backup everything
wo site backup example.com

# Backup database only
wo site backup example.com --db

# Backup files only
wo site backup example.com --files
```

---

### Site Clone

**Usage:** `wo site clone <source> <destination> [options]`

**Description:** Clone a site to a new domain.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `source` | Positional (required) | Source domain name |
| `destination` | Positional (required) | Destination domain name |
| `--letsencrypt` | Flag | Configure Let's Encrypt for cloned site |
| `--hsts` | Flag | Enable HSTS for cloned site |

**Examples:**

```bash
# Clone site
wo site clone example.com example.net

# Clone with SSL
wo site clone example.com example.net --letsencrypt
```

---

### Site Restore

**Usage:** `wo site restore <sitename> [options]`

**Description:** Restore site from backup.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to restore |
| `--files` | Flag | Restore files only |
| `--db` | Flag | Restore database only |
| `--all` | Flag | Restore files and database (default) |

**Examples:**

```bash
# Restore everything
wo site restore example.com

# Restore database only
wo site restore example.com --db
```

---

### Site Secure

**Usage:** `wo site secure <sitename> [options]`

**Description:** Secure site with authentication and IP whitelisting.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `sitename` | Positional (required) | Domain name to secure |
| `--auth` | Value | Enable HTTP authentication (basic/digest) |
| `--user` | Value | Username for authentication |
| `--pass` | Value | Password for authentication |
| `--whitelist` | Value | Whitelist IP addresses |
| `--port` | Value | Change backend port |

**Examples:**

```bash
# Enable basic auth
wo site secure example.com --auth=basic --user=admin --pass=secret

# Whitelist IPs
wo site secure example.com --whitelist=1.2.3.4,5.6.7.8
```

---

## Stack

**Command:** `wo stack`

**Description:** Install, remove, purge, upgrade, or migrate server stack components.

### Subcommands

### Stack Install

**Usage:** `wo stack install [options]`

**Description:** Install server stack components.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--all` | Flag | Install all stack components |
| `--web` | Flag | Install web stack (Nginx, PHP, MySQL) |
| `--admin` | Flag | Install admin tools (phpMyAdmin, Adminer, etc.) |
| `--security` | Flag | Install security stack (fail2ban, ngxblocker) |
| `--nginx` | Flag | Install Nginx |
| `--php` | Flag | Install default PHP (8.4) |
| `--php74` | Flag | Install PHP 7.4 |
| `--php80` | Flag | Install PHP 8.0 |
| `--php81` | Flag | Install PHP 8.1 |
| `--php82` | Flag | Install PHP 8.2 |
| `--php83` | Flag | Install PHP 8.3 |
| `--php84` | Flag | Install PHP 8.4 |
| `--mysql` | Flag | Install MariaDB |
| `--mariadb` | Flag | Install MariaDB (alias) |
| `--wpcli` | Flag | Install WP-CLI |
| `--redis` | Flag | Install Redis |
| `--fail2ban` | Flag | Install Fail2Ban |
| `--proftpd` | Flag | Install ProFTPD |
| `--netdata` | Flag | Install Netdata monitoring |
| `--dashboard` | Flag | Install WordOps dashboard |
| `--composer` | Flag | Install Composer |
| `--phpmyadmin` | Flag | Install phpMyAdmin |
| `--adminer` | Flag | Install Adminer |
| `--mysqltuner` | Flag | Install MySQLTuner |
| `--ngxblocker` | Flag | Install Nginx Bad Bot Blocker |
| `--ufw` | Flag | Install UFW firewall |
| `--sendmail` | Flag | Install Sendmail |
| `--clamav` | Flag | Install ClamAV antivirus |
| `--force` | Flag | Force installation without confirmation |

**Examples:**

```bash
# Install web stack
wo stack install --web

# Install specific PHP versions
wo stack install --php81 --php82

# Install admin tools
wo stack install --admin

# Install everything
wo stack install --all
```

---

### Stack Remove

**Usage:** `wo stack remove [options]`

**Description:** Remove stack components (keeps configuration files).

**Arguments:**

Same as Stack Install arguments.

**Examples:**

```bash
# Remove Redis
wo stack remove --redis

# Remove PHP 7.4
wo stack remove --php74
```

---

### Stack Purge

**Usage:** `wo stack purge [options]`

**Description:** Purge stack components (removes configuration files).

**Arguments:**

Same as Stack Install arguments plus:

| Argument | Type | Description |
|----------|------|-------------|
| `--force` | Flag | Force purge without confirmation |

**Examples:**

```bash
# Purge Redis (removes config)
wo stack purge --redis

# Purge without confirmation
wo stack purge --redis --force
```

---

### Stack Migrate

**Usage:** `wo stack migrate [options]`

**Description:** Migrate stack components safely.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--mariadb` | Flag | Migrate/upgrade to latest MariaDB |
| `--nginx` | Flag | Migrate Nginx to HTTP/3 QUIC |
| `--force` | Flag | Force migration without confirmation |
| `--ci` | Flag | Testing argument (do not use) |

**Examples:**

```bash
# Migrate MariaDB
wo stack migrate --mariadb

# Migrate Nginx to HTTP/3
wo stack migrate --nginx
```

---

### Stack Upgrade

**Usage:** `wo stack upgrade [options]`

**Description:** Upgrade stack components to latest versions.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--all` | Flag | Upgrade all stack components |
| `--web` | Flag | Upgrade web stack |
| `--admin` | Flag | Upgrade admin tools |
| `--security` | Flag | Upgrade security stack |
| `--nginx` | Flag | Upgrade Nginx |
| `--php` | Flag | Upgrade default PHP |
| `--php74` | Flag | Upgrade PHP 7.4 |
| `--php80` | Flag | Upgrade PHP 8.0 |
| `--php81` | Flag | Upgrade PHP 8.1 |
| `--php82` | Flag | Upgrade PHP 8.2 |
| `--php83` | Flag | Upgrade PHP 8.3 |
| `--php84` | Flag | Upgrade PHP 8.4 |
| `--mysql` | Flag | Upgrade MariaDB |
| `--mariadb` | Flag | Upgrade MariaDB (alias) |
| `--wpcli` | Flag | Upgrade WP-CLI |
| `--redis` | Flag | Upgrade Redis |
| `--netdata` | Flag | Upgrade Netdata |
| `--fail2ban` | Flag | Upgrade Fail2Ban |
| `--dashboard` | Flag | Upgrade WordOps dashboard |
| `--composer` | Flag | Upgrade Composer |
| `--mysqltuner` | Flag | Upgrade MySQLTuner |
| `--phpmyadmin` | Flag | Upgrade phpMyAdmin |
| `--adminer` | Flag | Upgrade Adminer |
| `--ngxblocker` | Flag | Upgrade Nginx Bad Bot Blocker |
| `--no-prompt` | Flag | Upgrade without confirmation |
| `--force` | Flag | Force upgrade without confirmation |

**Examples:**

```bash
# Upgrade all components
wo stack upgrade --all

# Upgrade web stack
wo stack upgrade --web

# Upgrade specific components
wo stack upgrade --nginx --php82
```

---

### Stack Services

**Description:** Control stack services (start, stop, restart, reload, status).

#### Start Services

**Usage:** `wo stack start [options]`

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--nginx` | Flag | Start Nginx |
| `--php` | Flag | Start default PHP-FPM |
| `--php74` | Flag | Start PHP 7.4-FPM |
| `--php80` | Flag | Start PHP 8.0-FPM |
| `--php81` | Flag | Start PHP 8.1-FPM |
| `--php82` | Flag | Start PHP 8.2-FPM |
| `--php83` | Flag | Start PHP 8.3-FPM |
| `--php84` | Flag | Start PHP 8.4-FPM |
| `--mysql` | Flag | Start MariaDB |
| `--redis` | Flag | Start Redis |
| `--fail2ban` | Flag | Start Fail2Ban |
| `--proftpd` | Flag | Start ProFTPD |
| `--netdata` | Flag | Start Netdata |
| `--ufw` | Flag | Check UFW status |

**Default:** If no flags specified, starts Nginx, PHP, MySQL, Fail2Ban, Netdata, and UFW.

**Examples:**

```bash
# Start all services
wo stack start

# Start specific service
wo stack start --nginx
```

#### Stop Services

**Usage:** `wo stack stop [options]`

**Arguments:** Same as Start Services

**Examples:**

```bash
# Stop all services
wo stack stop

# Stop specific service
wo stack stop --mysql
```

#### Restart Services

**Usage:** `wo stack restart [options]`

**Arguments:** Same as Start Services

**Examples:**

```bash
# Restart all services
wo stack restart

# Restart Nginx
wo stack restart --nginx
```

#### Reload Services

**Usage:** `wo stack reload [options]`

**Arguments:** Same as Start Services

**Examples:**

```bash
# Reload Nginx configuration
wo stack reload --nginx

# Reload PHP-FPM
wo stack reload --php
```

#### Status Services

**Usage:** `wo stack status [options]`

**Arguments:** Same as Start Services

**Examples:**

```bash
# Check all services status
wo stack status

# Check specific service
wo stack status --nginx
```

---

## Sync

**Command:** `wo sync`

**Description:** Synchronize the WordOps database with actual site configurations.

**Usage:** `wo sync`

**Description:** Reads database information from wp-config.php/wo-config.php and updates WordOps database records accordingly.

**Examples:**

```bash
wo sync
```

---

## Update

**Command:** `wo update`

**Description:** Update WordOps to the latest version.

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `--force` | Flag | Force update without confirmation |
| `--beta` | Flag | Update to latest mainline (beta) release |
| `--mainline` | Flag | Update to latest mainline release |
| `--branch` | Value | Update from specific repository branch |
| `--travis` | Flag | Testing argument (development only) |

**Examples:**

```bash
# Update to latest stable version
wo update

# Update to mainline version
wo update --mainline

# Update from specific branch
wo update --branch=develop

# Force update without confirmation
wo update --force
```

---

## Common Patterns

### Default Behavior

Many commands have default behavior when no flags are specified:

- **`wo stack start/stop/restart/status`** - Operates on all main services (Nginx, PHP, MySQL, Fail2Ban, Netdata)
- **`wo stack install/upgrade`** - Without flags, installs/upgrades web + admin + security stacks
- **`wo clean`** - Without flags, cleans all cache types
- **`wo debug`** - Without flags, enables all debug options
- **`wo info`** - Without flags, shows all information

### PHP Version Handling

PHP version can be specified in multiple ways:

```bash
# During site creation
wo site create example.com --wp --php82

# Update existing site
wo site update example.com --php83

# Install specific PHP version
wo stack install --php81
```

### SSL Certificate Options

```bash
# Basic Let's Encrypt
wo site create example.com --wp --letsencrypt

# Wildcard certificate with DNS API
wo site create example.com --wp --letsencrypt=wildcard --dns=dns_cf

# With HSTS enabled
wo site create example.com --wp --letsencrypt --hsts

# Remove SSL
wo site update example.com --letsencrypt=off
```

### Cache Types

WordPress sites support multiple cache mechanisms:

- **FastCGI Cache:** `--wpfc` (recommended for most sites)
- **Redis Cache:** `--wpredis` (for high-traffic sites)
- **WP Super Cache:** `--wpsc` (plugin-based)
- **Cache Enabler:** `--wpce` (plugin-based)
- **WP-Rocket:** `--wprocket` (premium plugin)

### Cache Transitions

You can switch between cache types easily:

```bash
# Start with basic WordPress
wo site create example.com --wp

# Add FastCGI cache
wo site update example.com --wpfc

# Switch to Redis cache
wo site update example.com --wpredis

# Remove cache (back to basic)
wo site update example.com --wp
```

---

## File Locations

### Site Files

- **Webroot:** `/var/www/{sitename}/`
- **Nginx config:** `/etc/nginx/sites-available/{sitename}`
- **Logs:** `/var/www/{sitename}/logs/`
- **SSL certificates:** `/etc/letsencrypt/live/{sitename}/`
- **PHP-FPM pool:** `/etc/php/{version}/fpm/pool.d/{sitename-slug}.conf`

### Configuration Files

- **Nginx main:** `/etc/nginx/nginx.conf`
- **PHP-FPM:** `/etc/php/{version}/fpm/`
- **MariaDB:** `/etc/mysql/`
- **WordOps config:** `/etc/wo/wo.conf`
- **WordOps database:** `/var/lib/wo/dbase.db`

### Backend Access

- **URL:** `https://your-server-ip:22222`
- **Credentials:** Displayed after installation or in `/var/www/22222/`

---

## Architecture Details

### Per-Site User Isolation

Each site gets its own dedicated system user and PHP-FPM pool:

**Example for `example.com`:**
- **Domain:** `example.com`
- **Slug:** `example-com` (dots → dashes, lowercase)
- **User:** `php-example-com`
- **Group:** `php-example-com`
- **Pool name:** `example-com`
- **Socket:** `/run/php/php84-fpm-example-com.sock`
- **Service:** `php8.4-fpm@example-com`

### PHP Version Changes

When changing PHP versions (e.g., 8.3 → 8.4):
- ✅ **User preserved** - `php-example-com` stays the same
- ✅ **Old pool removed** - `php8.3-fpm@example-com` stopped and removed
- ✅ **New pool created** - `php8.4-fpm@example-com` started
- ✅ **File permissions maintained** - webroot still owned by `php-example-com`
- ✅ **Nginx config updated** - points to new socket path

### Visual Regression Testing (Autoupdate)

The `wo site autoupdate` feature uses BackstopJS to detect visual changes:

1. **Baseline:** Takes screenshots before updates
2. **Update:** Applies WordPress and plugin updates
3. **Compare:** Takes new screenshots and compares
4. **Report:** Generates visual diff report
5. **Cleanup:** Removes old backstop_data after successful updates

---

## Notes

1. **Root Privileges:** All WordOps commands require root/sudo privileges.

2. **Database Backup:** Before major operations (migrate, upgrade), WordOps automatically backs up databases.

3. **Git Integration:** Configuration changes are tracked in Git for easy rollback.

4. **Service Management:** WordOps uses systemd for service management.

5. **Platform Support:** WordOps supports Ubuntu (20.04+, 22.04) and Debian (10, 11, 12).

6. **PHP Versions:** Multiple PHP versions can coexist. Each site can use a different version.

7. **Site Isolation:** Each site runs as its own user with dedicated PHP-FPM pool for security.

8. **Zero Downtime:** PHP version changes happen without downtime - new pool starts before old one stops.

---

## Related Files

All plugin source files are located in `wo/cli/plugins/`:

- `clean.py` - Clean cache commands
- `debug.py` - Debug commands
- `import_slow_log.py` - MySQL slow log import
- `info.py` - Information display
- `log.py` - Log management
- `maintenance.py` - Maintenance mode
- `secure_ssh.py` - SSH security
- `site.py` - Site base commands
- `site_create.py` - Site creation
- `site_update.py` - Site updates (✅ FIXED - all critical bugs resolved)
- `site_backup.py` - Backup operations
- `site_clone.py` - Clone operations
- `site_restore.py` - Restore operations
- `site_secure.py` - Site security
- `site_autoupdate.py` - Auto-update management with visual regression
- `stack.py` - Stack base commands (✅ Refactored version available)
- `stack_migrate.py` - Migration operations
- `stack_upgrade.py` - Upgrade operations (✅ FIXED - all critical bugs resolved)
- `stack_services.py` - Service management
- `stack_pref.py` - Stack preferences and configurations
- `sync.py` - Database synchronization
- `update.py` - WordOps self-update (✅ Refactored version available)

---

**Document Version:** 1.0
**WordOps Version Analyzed:** 3.22.0+
**Last Updated:** 2025-10-21
**Analysis Status:** ✅ All critical bugs in core plugins have been fixed!
