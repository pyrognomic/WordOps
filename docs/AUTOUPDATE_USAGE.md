# WordOps Auto-Update Usage Guide (Code-Accurate)

This guide documents the current implementation in `wo/cli/plugins/site_autoupdate.py`.

## Overview

`wo site autoupdate` is a WordPress-focused update orchestration command that combines:
- update detection (core/plugins/themes)
- pre-change backup
- update execution
- optional visual regression checks
- rollback on failure

It is built around three subcommands:
- `run`
- `schedule`
- `backstop`

## Command Surface

### Run updates

```bash
wo site autoupdate run <site_name> [--dry-run] [--no-visual] [--backup-dir DIR]
wo site autoupdate run --all [--dry-run] [--no-visual] [--backup-dir DIR]
```

### Install/remove schedule

```bash
wo site autoupdate schedule --enable [--interval=hourly|daily]
wo site autoupdate schedule --disable
```

### Configure BackstopJS scaffold

```bash
wo site autoupdate backstop <site_name> [--urls CSV] [--urls-file FILE] [--reference] [--approve]
wo site autoupdate backstop --all [--urls CSV] [--urls-file FILE] [--reference] [--approve]
```

## Run Pipeline (Actual Flow)

For each targeted site:
1. Acquire lock (`/run/wo-autoupdate.lock` global, `/run/wo-autoupdate-<slug>.lock` site).
2. Ensure site is WordPress type (`'wp' in site_type`).
3. Detect updates using WordPress update APIs via `wp eval`:
   - `get_core_updates()`
   - `get_plugin_updates()`
   - `get_theme_updates()`
4. If `--dry-run`, return summary only (`planned` or `noop`).
5. Create full backup using `WOBackup` (`wo/core/backup.py`).
6. If no updates are pending, stop with status `backup-only`.
7. If `conf/backstop.config.js` exists, generate pre-update Backstop reference.
8. Apply updates:
   - `wp core update`
   - `wp plugin update --all`
   - `wp theme update --all`
9. If visual checks are enabled, execute hook command from `conf/autoupdate-visual-cmd`.
10. If update or visual step fails, attempt restore with `wo site restore <archive>`.
11. Write summary JSON in `/var/log/wo/autoupdate/run-<timestamp>.json`.

## Flags and Behavior

- `--dry-run`
  - Detects updates and reports plan; does not backup/update.
- `--no-visual`
  - Skips the visual hook execution step.
- `--backup-dir`
  - Overrides backup root path.
- `--all`
  - Targets all WordPress sites only.

Important: Current code does **not** implement a `--backup-only` CLI flag.
The command still creates backups even when no updates exist (result status `backup-only`).

## BackstopJS Integration

### Scaffold output

`wo site autoupdate backstop` generates:
- `<site_path>/conf/backstop.config.js`
- `<site_path>/conf/autoupdate-visual-cmd`

By default, `autoupdate-visual-cmd` contains:
```bash
npx backstop test --config={{config_path}} --report=CI
```

### URL scenario generation

Sources:
- `--urls` (comma-separated paths)
- `--urls-file` (one path per line)

Fallback:
- `/` if neither is provided

Generated scenario defaults:
- viewports: phone + desktop
- `misMatchThreshold`: `0.05`
- `requireSameDimensions`: `true`

### Baseline control

- `--reference`: run `npx backstop reference` immediately after scaffold
- `--approve`: run `npx backstop approve` immediately after scaffold

### Autoupdate interaction

During `run`, if a Backstop config exists, code generates a fresh pre-update reference before applying updates.
After updates, the hook command is executed. Non-zero exit triggers rollback attempt.

## Scheduling (`schedule`)

Enable path deploys and enables:
- `/etc/systemd/system/wo-autoupdate.service`
- `/etc/systemd/system/wo-autoupdate.timer`

Disable path stops timer and removes both files.

`--interval=hourly|daily` maps to timer `OnCalendar`.

Implementation detail:
- `schedule` parses `--enable/--disable/--interval` from raw argv.

## Logs and State

Per-site logs:
- `/var/log/wo/autoupdate/<slug>/core.log`
- `/var/log/wo/autoupdate/<slug>/plugins.log`
- `/var/log/wo/autoupdate/<slug>/themes.log`
- `/var/log/wo/autoupdate/<slug>/visual-regression.log`

Run summaries:
- `/var/log/wo/autoupdate/run-<timestamp>.json`

Retention behavior in code:
- keeps latest 5 run summary files
- keeps latest 5 Backstop test bitmap directories

## Locking

Lock files:
- `/run/wo-autoupdate.lock`
- `/run/wo-autoupdate-<slug>.lock`

Stale lock recovery:
- lock includes PID + timestamp
- stale locks can be auto-recovered when age/PID checks indicate stale state

## WP-CLI Execution Security Model

Autoupdate executes WP-CLI as the site's isolated PHP-FPM user (`php-<slug>`):
- Requires root execution context.
- Performs uid/gid demotion for subprocess calls.
- Prepares site-specific `/tmp/wp-cli-<slug>` HOME/cache paths.

This keeps ownership/permissions consistent with per-site isolation.

## Examples

### 1. Inspect updates only

```bash
wo site autoupdate run app.example.com --dry-run
```

### 2. Update a single site with visual checks

```bash
wo site autoupdate backstop app.example.com --urls /,/about,/contact --reference
wo site autoupdate run app.example.com
```

### 3. Update all WordPress sites without visual step

```bash
wo site autoupdate run --all --no-visual
```

### 4. Use external backup storage

```bash
wo site autoupdate run --all --backup-dir /mnt/backup/wordops
```

### 5. Enable daily scheduled updates

```bash
wo site autoupdate schedule --enable --interval=daily
systemctl status wo-autoupdate.timer
```

## Troubleshooting

### Visual failures

- Inspect: `<site_path>/conf/backstop_data/html_report/` and per-site visual log.
- If failure was expected (intentional UI change), regenerate/approve baseline and rerun.

### Update failures

- Check per-site logs in `/var/log/wo/autoupdate/<slug>/`.
- Check WordOps log: `/var/log/wo/wordops.log`.
- Validate restore path from summary archive value.

### Lock contention

- If command says another run is in progress, verify active processes first.
- Remove stale lock file only after confirming no active run.

## Related Files

- `wo/cli/plugins/site_autoupdate.py`
- `wo/cli/templates/backstop.config.js.mustache`
- `wo/cli/templates/autoupdate-visual-cmd.mustache`
- `wo/core/backup.py`
- `docs/BACKUP_ARCHITECTURE.md`
