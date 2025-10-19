# WordOps Backup Architecture

## Overview

WordOps uses a **centralized backup service** (`wo.core.backup.WOBackup`) to handle all backup operations across different modules. This ensures consistency, reduces code duplication, and makes backups more maintainable.

## Architecture

```
┌─────────────────────────────────────────────────┐
│           Backup Consumers                      │
├─────────────────────────────────────────────────┤
│  • site_backup.py    - Manual backups           │
│  • site_autoupdate.py - Pre-update backups      │
│  • site_update.py    - Pre-database/file updates│
│  • Any custom modules requiring backups         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│        WOBackup (Centralized Service)           │
│         wo/core/backup.py                       │
├─────────────────────────────────────────────────┤
│  • Single source of truth for backup logic      │
│  • Handles full/db/files backup types           │
│  • Manages metadata and archiving               │
│  • Provides list/info utilities                 │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│          Shared Utilities                       │
│      wo/cli/plugins/site_functions.py           │
├─────────────────────────────────────────────────┤
│  • create_database_backup()                     │
│  • collect_site_metadata()                      │
│  • create_site_archive()                        │
└─────────────────────────────────────────────────┘
```

## Backup Types

The `WOBackup` service supports three backup types:

### 1. Full Backup (`TYPE_FULL`)
- **What it backs up:**
  - All files in `htdocs/`
  - Configuration files (`*-config.php`, `wp-config.php`)
  - Database dump (`.sql` file)
  - Site metadata (`vhost.json`)
- **When to use:**
  - Before major updates (WordPress core, plugins, themes)
  - Before site modifications
  - Manual full backups
- **Example:**
  ```python
  backup = WOBackup(self, siteinfo)
  success, archive = backup.create(
      backup_type=WOBackup.TYPE_FULL,
      reason='pre-core-update'
  )
  ```

### 2. Database Only (`TYPE_DATABASE`)
- **What it backs up:**
  - Database dump only
  - Metadata
- **When to use:**
  - Before database migrations
  - Before running SQL updates
  - Quick database snapshots
- **Example:**
  ```python
  backup = WOBackup(self, siteinfo)
  success, archive = backup.create(
      backup_type=WOBackup.TYPE_DATABASE,
      reason='pre-db-migration'
  )
  ```

### 3. Files Only (`TYPE_FILES`)
- **What it backs up:**
  - All files in `htdocs/`
  - Configuration files
  - Metadata (no database)
- **When to use:**
  - Before file-only operations
  - Theme/plugin file modifications
  - File system changes
- **Example:**
  ```python
  backup = WOBackup(self, siteinfo)
  success, archive = backup.create(
      backup_type=WOBackup.TYPE_FILES,
      reason='pre-file-update'
  )
  ```

## Usage Examples

### Example 1: Pre-Update Backup (site_autoupdate.py)

```python
from wo.core.backup import WOBackup

def _backup_site(self, siteinfo, backup_root=None, update_info=None):
    """Create a pre-update backup."""
    backup_service = WOBackup(self, siteinfo)

    # Prepare metadata about what's being updated
    metadata_extra = {
        'backup_type': 'pre-autoupdate',
        'autoupdate_timestamp': _now_ts()
    }

    if update_info:
        metadata_extra['pending_updates'] = update_info

    success, archive = backup_service.create(
        backup_type=WOBackup.TYPE_FULL,
        backup_root=backup_root,
        reason='pre-autoupdate',
        metadata_extra=metadata_extra
    )

    return success, archive
```

### Example 2: Manual Backup (site_backup.py)

```python
from wo.core.backup import WOBackup

def _backup_site(self, site, backup_root=None, backup_db=True, backup_files=True):
    """Manual backup with user-specified options."""
    siteinfo = getSiteInfo(self, site)

    # Determine backup type based on flags
    if backup_db and backup_files:
        backup_type = WOBackup.TYPE_FULL
    elif backup_db:
        backup_type = WOBackup.TYPE_DATABASE
    elif backup_files:
        backup_type = WOBackup.TYPE_FILES

    backup_service = WOBackup(self, siteinfo)
    success, archive = backup_service.create(
        backup_type=backup_type,
        backup_root=backup_root,
        reason='manual-backup'
    )

    return success
```

### Example 3: Pre-Database Update Backup

```python
from wo.core.backup import WOBackup

def update_database(self, siteinfo):
    """Update database with pre-update backup."""
    # Create backup before database update
    backup = WOBackup(self, siteinfo)
    success, archive = backup.create(
        backup_type=WOBackup.TYPE_DATABASE,
        reason='pre-db-update',
        metadata_extra={
            'operation': 'database_update',
            'db_name': siteinfo.db_name
        }
    )

    if not success:
        Log.error(self, "Failed to create pre-update backup")
        return False

    # Proceed with database update
    try:
        # ... perform database update ...
        return True
    except Exception as e:
        Log.error(self, f"Database update failed: {str(e)}")
        # Optionally restore from archive
        return False
```

## Backup Metadata

Each backup includes a `vhost.json` metadata file with:

### Standard Metadata (from `collect_site_metadata()`)
- Site ID, name, type, cache type
- Site path, creation date
- SSL status, enabled status
- Database name, user, host
- PHP version
- Storage filesystem type

### Backup-Specific Metadata
- `backup_timestamp`: ISO 8601 timestamp
- `backup_reason`: Why the backup was created
- Custom fields via `metadata_extra` parameter

### Example Metadata

```json
{
  "id": 5,
  "sitename": "example.com",
  "site_type": "wp",
  "cache_type": "wpfc",
  "site_path": "/var/www/example.com",
  "created_on": "2025-01-15T10:30:00",
  "is_enabled": 1,
  "is_ssl": 1,
  "db_name": "wo_example_com",
  "db_user": "wo_example",
  "db_host": "localhost",
  "php_version": "8.2",
  "backup_timestamp": "2025-01-20T14:25:30",
  "backup_reason": "pre-autoupdate",
  "backup_type": "pre-autoupdate",
  "pending_updates": {
    "core": false,
    "plugins": ["akismet", "jetpack"],
    "themes": ["twentytwentyfour"]
  }
}
```

## Backup Storage Structure

```
/var/www/example.com/backup/          (default backup root)
└── example.com/                       (domain directory)
    ├── 2025-01-20_14-25-30.tar.zst   (compressed archive)
    ├── 2025-01-19_10-15-22.tar.zst
    └── 2025-01-18_09-45-11.tar.zst

# Custom backup root (e.g., external storage)
/backup/wordops/                       (custom root)
└── example.com/
    ├── 2025-01-20_14-25-30.tar.zst
    └── ...
```

### Archive Contents

Each `.tar.zst` archive contains:

```
2025-01-20_14-25-30/
├── htdocs/                    (all website files)
│   ├── index.php
│   ├── wp-admin/
│   ├── wp-content/
│   └── ...
├── example.com-config.php     (configuration file)
├── example.com.sql            (database dump)
└── vhost.json                 (metadata)
```

## Backup Utility Functions

### List Available Backups

```python
from wo.core.backup import WOBackup

backups = WOBackup.list_backups(
    backup_root='/var/www/example.com/backup',
    site_name='example.com'
)

# Returns list of archive paths, newest first
# ['/var/www/example.com/backup/example.com/2025-01-20_14-25-30.tar.zst', ...]
```

### Get Backup Information

```python
from wo.core.backup import WOBackup

info = WOBackup.get_backup_info(
    '/var/www/example.com/backup/example.com/2025-01-20_14-25-30.tar.zst'
)

# Returns metadata dict with archive info
# {
#   'sitename': 'example.com',
#   'backup_reason': 'pre-autoupdate',
#   'archive_path': '/var/www/.../2025-01-20_14-25-30.tar.zst',
#   'archive_size': 52428800,  # bytes
#   'archive_mtime': 1705761930.5,
#   ...
# }
```

## Best Practices

### 1. Always Backup Before Destructive Operations

```python
# ✅ GOOD - Backup before update
backup = WOBackup(self, siteinfo)
success, archive = backup.create(backup_type=WOBackup.TYPE_FULL)
if success:
    perform_update()
else:
    Log.error(self, "Backup failed, aborting update")

# ❌ BAD - Update without backup
perform_update()  # Risky!
```

### 2. Include Relevant Metadata

```python
# ✅ GOOD - Descriptive metadata
backup.create(
    backup_type=WOBackup.TYPE_FULL,
    reason='pre-wordpress-6.5-update',
    metadata_extra={
        'wordpress_old_version': '6.4.2',
        'wordpress_new_version': '6.5.0',
        'updated_by': 'autoupdate-script'
    }
)

# ❌ BAD - No context
backup.create(backup_type=WOBackup.TYPE_FULL)
```

### 3. Use Appropriate Backup Type

```python
# ✅ GOOD - Database-only for DB operations
if operation_type == 'database':
    backup_type = WOBackup.TYPE_DATABASE

# ❌ BAD - Full backup for database-only change (wastes time/space)
backup.create(backup_type=WOBackup.TYPE_FULL)  # Overkill
```

### 4. Handle Backup Failures

```python
# ✅ GOOD - Check backup success
success, archive = backup.create(...)
if not success:
    Log.error(self, "Cannot proceed without backup")
    return False

# ❌ BAD - Ignore backup result
backup.create(...)
perform_risky_operation()  # Might fail without rollback option
```

### 5. Custom Backup Locations for Automation

```python
# ✅ GOOD - External storage for scheduled backups
backup.create(
    backup_root='/mnt/backup-storage/wordops',  # External mount
    reason='scheduled-backup'
)

# ℹ️ OK - Default location for manual backups
backup.create(reason='manual')  # Uses site_path/backup
```

## Migration from Old Code

### Before (Duplicated Code)

```python
# In site_autoupdate.py
def _backup_site(self, siteinfo):
    # 50+ lines of duplicated backup logic
    WOFileUtils.mkdir(...)
    WOFileUtils.copyfiles(...)
    create_database_backup(...)
    collect_site_metadata(...)
    create_site_archive(...)
    # ...

# In site_backup.py
def _backup_site(self, site):
    # Another 50+ lines of similar logic (DRY violation)
    # ...
```

### After (Centralized Service)

```python
# In site_autoupdate.py
from wo.core.backup import WOBackup

def _backup_site(self, siteinfo, update_info=None):
    backup = WOBackup(self, siteinfo)
    return backup.create(
        backup_type=WOBackup.TYPE_FULL,
        reason='pre-autoupdate',
        metadata_extra={'pending_updates': update_info}
    )

# In site_backup.py
from wo.core.backup import WOBackup

def _backup_site(self, site, backup_db=True, backup_files=True):
    siteinfo = getSiteInfo(self, site)
    backup_type = self._determine_backup_type(backup_db, backup_files)
    backup = WOBackup(self, siteinfo)
    return backup.create(backup_type=backup_type, reason='manual-backup')
```

## Benefits of Centralized Approach

1. **DRY (Don't Repeat Yourself)**: Single implementation, multiple consumers
2. **Consistency**: All backups use the same format and structure
3. **Maintainability**: Fix bugs once, all modules benefit
4. **Testability**: Test backup logic in isolation
5. **Extensibility**: Easy to add new backup types or features
6. **Metadata**: Consistent metadata tracking across all backups
7. **Utilities**: Built-in functions to list and inspect backups

## Future Enhancements

Potential improvements to the backup service:

1. **Incremental Backups**: Only backup changed files
2. **Retention Policies**: Auto-delete old backups
3. **Cloud Storage**: Direct upload to S3/B2/etc
4. **Encryption**: Encrypted backup archives
5. **Verification**: Post-backup integrity checks
6. **Parallel Compression**: Faster archiving
7. **Progress Callbacks**: UI progress bars
8. **Backup Rotation**: Keep N most recent backups

## See Also

- `wo/core/backup.py` - Backup service implementation
- `wo/cli/plugins/site_functions.py` - Shared backup utilities
- `wo/cli/plugins/site_backup.py` - Manual backup commands
- `wo/cli/plugins/site_autoupdate.py` - Auto-update with backups
