# WordOps Auto-Update Usage Guide

## Overview

`site_autoupdate.py` provides **automated WordPress updates with intelligent backup and rollback**. It solves the problem of safely keeping WordPress sites updated while protecting against breaking changes.

## How It Works (Current Implementation)

### The Perfect Flow ✅

```
1. Check for WordPress updates (core, plugins, themes)
   ↓
2. Create full backup (files + database)
   ↓ (if backup fails, ABORT)
3. Apply all updates
   ↓ (if updates fail, RESTORE backup)
4. Run visual regression test (optional)
   ↓ (if visual test fails, RESTORE backup)
5. Success - keep backup for safety
```

### Key Features

✅ **Always backups before updates** - No updates without a safety net
✅ **Automatic rollback** - Restores backup if anything fails
✅ **Visual regression testing** - Detects layout breaking changes
✅ **Detailed logging** - Track what was updated and why
✅ **Batch processing** - Update all sites at once
✅ **Locking mechanism** - Prevents concurrent updates

## Usage Examples

### Basic Usage

```bash
# Check what updates are available (no changes)
wo site autoupdate run example.com --dry-run

# Update with automatic backup and rollback protection
wo site autoupdate run example.com

# Update without visual regression test (faster)
wo site autoupdate run example.com --no-visual

# Update all WordPress sites
wo site autoupdate run --all
```

### Content Protection (NEW!)

Even when there are no WordPress updates, you can use autoupdate to create backups for content protection:

```bash
# Create backup even if no WordPress updates available
# Useful for protecting content changes (posts, media, etc.)
wo site autoupdate run example.com --backup-only

# Backup all sites regardless of update status
wo site autoupdate run --all --backup-only
```

### Custom Backup Location

```bash
# Store backups on external storage
wo site autoupdate run example.com --backup-dir /mnt/external-backup

# Backup all sites to external storage
wo site autoupdate run --all --backup-dir /mnt/backup-server
```

### Scheduled Automatic Updates

```bash
# Enable automatic daily updates for all WordPress sites
wo site autoupdate schedule --enable --interval=daily

# Enable hourly updates
wo site autoupdate schedule --enable --interval=hourly

# Check timer status
systemctl status wo-autoupdate.timer

# View logs
journalctl -u wo-autoupdate.service

# Disable automatic updates
wo site autoupdate schedule --disable
```

## Understanding the Flags

| Flag | Purpose | When to Use |
|------|---------|-------------|
| `--dry-run` | Check for updates without applying them | Testing, planning |
| `--no-visual` | Skip visual regression testing | Faster updates, trusted updates |
| `--backup-dir` | Custom backup location | External storage, centralized backups |
| `--backup-only` | Backup even without WordPress updates | Content protection, scheduled backups |
| `--all` | Process all WordPress sites | Batch updates, automation |

## Complete Backup Strategy

### For WordPress Updates

**Your `site_autoupdate.py` handles this perfectly:**

```bash
# Manual update with backup
wo site autoupdate run example.com

# Scheduled automatic updates
wo site autoupdate schedule --enable --interval=daily
```

### For Content Changes

**Two approaches:**

#### Option 1: Scheduled Content Backups (Recommended)

Use cron for regular content protection:

```bash
# Add to crontab
crontab -e

# Daily content backup at 2 AM (even without WordPress updates)
0 2 * * * /usr/local/bin/wo site autoupdate run --all --backup-only --backup-dir /mnt/backup

# OR use traditional site backup
0 2 * * * /usr/local/bin/wo site backup --all
```

#### Option 2: Combine Both

```bash
# Use autoupdate for WordPress updates (automatic via systemd)
wo site autoupdate schedule --enable --interval=daily

# Use cron for additional content backups
0 2 * * * /usr/local/bin/wo site autoupdate run --all --backup-only
```

## Real-World Scenarios

### Scenario 1: Small Business Website

**Needs:** Simple, reliable protection

```bash
# Daily automatic WordPress updates with backups
wo site autoupdate schedule --enable --interval=daily

# Weekly content backup (regardless of updates)
# Add to crontab:
0 3 * * 0 /usr/local/bin/wo site autoupdate run --all --backup-only
```

### Scenario 2: E-commerce Site

**Needs:** Frequent content backups, careful updates

```bash
# Manual WordPress updates only (test first)
wo site autoupdate run shop.example.com --dry-run
wo site autoupdate run shop.example.com

# Hourly content backups
# Add to crontab:
0 * * * * /usr/local/bin/wo site backup shop.example.com --db
0 2 * * * /usr/local/bin/wo site backup shop.example.com
```

### Scenario 3: High-Traffic News Site

**Needs:** Real-time protection, minimal downtime

```bash
# Automatic daily updates in off-peak hours
wo site autoupdate schedule --enable --interval=daily

# Multiple daily content backups
# Add to crontab:
0 */6 * * * /usr/local/bin/wo site autoupdate run --all --backup-only --no-visual
```

### Scenario 4: Development/Staging Site

**Needs:** Frequent testing, less concern about content

```bash
# Aggressive update schedule
wo site autoupdate schedule --enable --interval=hourly

# No additional content backups needed
```

## Backup Retention

Backups are stored in:
```
/var/www/example.com/backup/example.com/
├── 2025-01-20_14-25-30.tar.zst  (latest)
├── 2025-01-20_02-00-15.tar.zst
├── 2025-01-19_14-30-22.tar.zst
└── ...
```

### Manual Cleanup

```bash
# List all backups for a site
ls -lth /var/www/example.com/backup/example.com/

# Keep only last 7 days of backups
find /var/www/example.com/backup/example.com/ \
  -name "*.tar.zst" -mtime +7 -delete

# Keep only last 10 backups
ls -t /var/www/example.com/backup/example.com/*.tar.zst | tail -n +11 | xargs rm -f
```

### Automated Retention (Recommended)

Create `/etc/cron.daily/wo-backup-cleanup`:

```bash
#!/bin/bash
#
# Cleanup old backups - keep last 30 days
#

BACKUP_ROOT="/var/www"
RETENTION_DAYS=30

find "$BACKUP_ROOT" -type f -name "*.tar.zst" -mtime +$RETENTION_DAYS -delete

echo "Backup cleanup completed: removed backups older than $RETENTION_DAYS days"
```

Make it executable:
```bash
chmod +x /etc/cron.daily/wo-backup-cleanup
```

## Monitoring and Logs

### Check Last Update Status

```bash
# View latest autoupdate run summary
cat /var/log/wo/autoupdate/run-*.json | tail -1 | jq '.'

# Check for failed updates
cat /var/log/wo/autoupdate/run-*.json | tail -1 | jq '.sites[] | select(.status=="error")'

# Count successful updates
cat /var/log/wo/autoupdate/run-*.json | tail -1 | jq '.sites[] | select(.status=="ok") | .site'
```

### View Individual Site Logs

```bash
# Autoupdate logs for specific site
ls -lth /var/log/wo/autoupdate/example-com/

# View core update log
cat /var/log/wo/autoupdate/example-com/core.log

# View plugin update log
cat /var/log/wo/autoupdate/example-com/plugins.log

# View visual regression log
cat /var/log/wo/autoupdate/example-com/visual-regression.log
```

### Alert on Failures

Create `/usr/local/bin/wo-autoupdate-check`:

```bash
#!/bin/bash

LAST_RUN=$(ls -t /var/log/wo/autoupdate/run-*.json | head -1)

FAILED=$(jq -r '.sites[] | select(.status=="error") | .site' "$LAST_RUN")

if [ -n "$FAILED" ]; then
    echo "Failed updates detected:"
    echo "$FAILED"

    # Send email alert (configure mail first)
    echo "$FAILED" | mail -s "WordOps Update Failures" admin@example.com

    exit 1
fi

echo "All updates successful"
exit 0
```

## Troubleshooting

### Update Failed - Site Broken

```bash
# Find the latest backup
LATEST_BACKUP=$(ls -t /var/www/example.com/backup/example.com/*.tar.zst | head -1)

# Restore it
wo site restore "$LATEST_BACKUP"
```

### Visual Regression Failed

```bash
# View the visual regression report
firefox /var/www/example.com/conf/backstop_data/html_report/index.html

# If false positive, approve the changes as new baseline
wo site autoupdate backstop example.com --approve

# Re-run update
wo site autoupdate run example.com
```

### Backup Failed

Check disk space and permissions:

```bash
# Check disk space
df -h /var/www/example.com/backup

# Check permissions
ls -ld /var/www/example.com/backup

# Fix permissions if needed
chown -R www-data:www-data /var/www/example.com/backup
chmod -R 755 /var/www/example.com/backup
```

### Update Stuck

```bash
# Check for lock files
ls -l /run/wo-autoupdate*.lock

# Remove stale locks (if process not running)
rm /run/wo-autoupdate.lock
rm /run/wo-autoupdate-example-com.lock

# Retry update
wo site autoupdate run example.com
```

## Best Practices

### 1. Always Test First

```bash
# Check what would be updated
wo site autoupdate run example.com --dry-run

# Test on staging first
wo site autoupdate run staging.example.com

# Then update production
wo site autoupdate run example.com
```

### 2. Backup to External Storage

```bash
# Mount external storage
mount /dev/sdb1 /mnt/backup-storage

# Use it for backups
wo site autoupdate run --all --backup-dir /mnt/backup-storage
```

### 3. Monitor Regularly

```bash
# Add monitoring cron job
echo "0 9 * * * /usr/local/bin/wo-autoupdate-check" | crontab -
```

### 4. Keep Multiple Backup Generations

```bash
# Keep 30 days of backups (automated cleanup)
# See "Automated Retention" section above
```

### 5. Use Visual Regression for Critical Sites

```bash
# Setup visual regression for important sites
wo site autoupdate backstop example.com --reference --urls /,/shop,/checkout

# Always run visual tests
wo site autoupdate run example.com  # (--no-visual NOT used)
```

## Summary

### The Simple Answer to Your Question

**Yes, `site_autoupdate.py` already does exactly what you described!**

✅ It **always creates a backup** before any WordPress updates
✅ It **checks for core, theme, and plugin updates**
✅ It **applies all updates**
✅ It **automatically restores the backup if anything fails**

### For Content Changes (Files/Database)

Since WordPress content changes continuously and unpredictably, use **scheduled backups**:

```bash
# Daily content backup (recommended)
0 2 * * * /usr/local/bin/wo site autoupdate run --all --backup-only

# OR traditional backup
0 2 * * * /usr/local/bin/wo site backup --all
```

### Complete Protection Strategy

```bash
# 1. Automatic WordPress updates with backups (handles core/plugins/themes)
wo site autoupdate schedule --enable --interval=daily

# 2. Daily content backups (handles all other changes)
# Add to crontab:
0 2 * * * /usr/local/bin/wo site autoupdate run --all --backup-only

# Done! You're fully protected.
```

## Quick Reference

```bash
# WordPress updates with backup
wo site autoupdate run example.com

# Content backup (no WordPress updates)
wo site autoupdate run example.com --backup-only

# Check for updates (no changes)
wo site autoupdate run example.com --dry-run

# Update all sites
wo site autoupdate run --all

# Schedule automatic updates
wo site autoupdate schedule --enable --interval=daily

# Restore from backup
wo site restore /var/www/example.com/backup/example.com/2025-01-20_14-25-30.tar.zst
```
