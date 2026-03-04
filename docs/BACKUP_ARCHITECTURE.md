# WordOps Backup Architecture (Current Implementation)

This document describes the backup system implemented in `wo/core/backup.py` and used by site controllers.

## Central Service

Primary class:
- `WOBackup` in `wo/core/backup.py`

Consumers:
- `wo site backup` (`wo/cli/plugins/site_backup.py`)
- `wo site autoupdate run` (`wo/cli/plugins/site_autoupdate.py`)
- other site workflows that call backup helpers

## Backup Types

- `WOBackup.TYPE_FULL`
- `WOBackup.TYPE_DATABASE`
- `WOBackup.TYPE_FILES`

## `WOBackup.create()` Flow

Inputs:
- `backup_type`
- `backup_root` (optional)
- `metadata_extra` (optional)

Processing:
1. Build timestamped target directory.
2. Backup files (`htdocs` + config files) when requested.
3. Backup database dump when requested.
4. Collect metadata and write `vhost.json`.
5. Archive timestamp folder into `.tar.zst`.
6. Return `(success, archive_path)`.

## File Layout

Default root:
- `<site_path>/backup/<sitename>/`

Archive naming:
- `<timestamp>.tar.zst`

Staged contents before compression:
- `htdocs/`
- `*-config.php` or `wp-config.php` if found
- `<sitename>.sql` when DB backup included
- `vhost.json`

## Metadata (`vhost.json`)

Collected by `collect_site_metadata()` in `site_functions.py`.
Includes:
- site identity and type/cache
- paths and flags (`is_enabled`, `is_ssl`)
- DB fields (`db_name`, `db_user`, `db_password`, `db_host`)
- php version and storage fields
- optional HTTP auth data from `/etc/nginx/acl/<slug>/credentials`
- caller-provided `metadata_extra`

Note:
- HTTP auth password in metadata is the hashed credential value from the credentials file.

## Related Helpers in `site_functions.py`

- `create_database_backup()`
- `collect_site_metadata()`
- `create_site_archive()`

## Backup And Restore Integration

- Manual backup command uses `WOBackup.create()` directly.
- Autoupdate creates a pre-update backup and may rollback with `wo site restore <archive>`.
- Restore command reads `vhost.json` and reconstructs site configuration/state.

Autoupdate-specific behavior:
- When updates are pending, autoupdate renames the created archive to include `_preupdate` suffix.
- Metadata includes `pending_updates` for core/plugins/themes in that run.
- If no updates are pending, autoupdate still creates a scheduled backup and exits with `backup-only` status.

## Useful Call Pattern

```python
backup_service = WOBackup(self, siteinfo)
success, archive = backup_service.create(
    backup_type=WOBackup.TYPE_FULL,
    backup_root='/mnt/backups',
    metadata_extra={'backup_type': 'manual'}
)
```

## Operational Notes

- Backup integrity depends on availability of `tar --zstd` and `mysqldump` (for DB backups).
- Keep backup directories on storage with sufficient capacity.
- Implement retention externally (cron/systemd) if needed; current core service does not enforce retention policy.

Restore expectation:
- A valid archive must contain `vhost.json`.
- Restore logic uses metadata to rebuild site record, nginx vhost/webroot state, ACL, and database restore inputs.
- For proxy/alias sites, restore is currently partial because upstream/alias target details are not fully reconstructed from metadata fields used by restore.
