"""
WordOps Backup Service
Centralized backup functionality for all WordOps site operations.

This module provides a unified backup interface used by:
- site_backup.py: Manual backup commands
- site_autoupdate.py: Pre-update backups
- site_update.py: Pre-database/file update backups
- Any other modules requiring site backups

Usage:
    from wo.core.backup import WOBackup

    backup = WOBackup(controller, siteinfo)
    success, archive_path = backup.create(
        backup_type='full',  # 'full', 'db', 'files'
        backup_root='/custom/path',
        reason='pre-update'
    )
"""

import glob
import json
import os
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.shellexec import WOShellExec
from wo.cli.plugins.site_functions import (
    create_database_backup,
    collect_site_metadata,
    create_site_archive,
)


class WOBackup:
    """Centralized backup service for WordOps sites."""

    # Backup types
    TYPE_FULL = 'full'
    TYPE_DATABASE = 'db'
    TYPE_FILES = 'files'

    def __init__(self, controller, siteinfo):
        """Initialize backup service.

        Args:
            controller: WordOps controller instance
            siteinfo: Site information object from sitedb
        """
        self.controller = controller
        self.siteinfo = siteinfo
        self.site_name = siteinfo.sitename

    @staticmethod
    def _timestamp():
        """Generate consistent timestamp format."""
        return datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')

    def create(
        self,
        backup_type: str = TYPE_FULL,
        backup_root: Optional[str] = None,
        metadata_extra: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Create a site backup.

        Args:
            backup_type: Type of backup ('full', 'db', 'files')
            backup_root: Custom backup directory (default: site_path/backup)
            metadata_extra: Additional metadata to include in backup

        Returns:
            Tuple of (success: bool, archive_path: str or None)

        Example:
            backup = WOBackup(self, siteinfo)
            success, archive = backup.create(
                backup_type='full',
                metadata_extra={'backup_type': 'manual', 'wordpress_version': '6.4.2'}
            )
        """
        if backup_type not in (self.TYPE_FULL, self.TYPE_DATABASE, self.TYPE_FILES):
            Log.error(self.controller, f"Invalid backup type: {backup_type}")
            return False, None

        timestamp = self._timestamp()
        root = backup_root if backup_root else os.path.join(
            self.siteinfo.site_path, 'backup'
        )
        domain_dir = os.path.join(root, self.site_name)
        target_dir = os.path.join(domain_dir, timestamp)

        try:
            WOFileUtils.mkdir(self.controller, target_dir)
        except Exception as e:
            Log.error(self.controller, f"Failed to create backup directory: {str(e)}")
            return False, None

        backup_success = True

        # Backup files if requested
        if backup_type in (self.TYPE_FULL, self.TYPE_FILES):
            if not self._backup_files(target_dir):
                backup_success = False

        # Backup database if requested
        if backup_type in (self.TYPE_FULL, self.TYPE_DATABASE):
            if not create_database_backup(
                self.controller, self.siteinfo, target_dir, self.site_name
            ):
                backup_success = False

        # Collect and save metadata
        if not self._save_metadata(target_dir, metadata_extra):
            backup_success = False

        # Create compressed archive
        archive_path = None
        if backup_success:
            if create_site_archive(self.controller, domain_dir, timestamp):
                archive_path = os.path.join(domain_dir, f'{timestamp}.tar.zst')
                Log.debug(
                    self.controller,
                    f"Backup completed: {archive_path}"
                )
            else:
                backup_success = False

        if not backup_success:
            Log.warn(
                self.controller,
                f"Backup completed with errors for {self.site_name}"
            )

        return backup_success, archive_path

    def _backup_files(self, target_dir: str) -> bool:
        """Backup site files (htdocs and config).

        Args:
            target_dir: Directory to store backup files

        Returns:
            bool: True if successful, False otherwise
        """
        success = True

        # Backup htdocs directory
        htdocs_src = os.path.join(self.siteinfo.site_path, 'htdocs')
        if os.path.isdir(htdocs_src):
            htdocs_dest = os.path.join(target_dir, 'htdocs')
            try:
                WOFileUtils.copyfiles(self.controller, htdocs_src, htdocs_dest)
                Log.debug(self.controller, f"Backed up htdocs to {htdocs_dest}")
            except Exception as e:
                Log.warn(self.controller, f'Failed to backup htdocs: {str(e)}')
                success = False

        # Backup configuration file(s)
        config_file = self._find_config_file()
        if config_file:
            try:
                config_dest = os.path.join(target_dir, os.path.basename(config_file))
                WOFileUtils.copyfile(self.controller, config_file, config_dest)
                Log.debug(self.controller, f"Backed up config to {config_dest}")
            except Exception as e:
                Log.warn(self.controller, f'Failed to backup config file: {str(e)}')
                success = False

        return success

    def _find_config_file(self) -> Optional[str]:
        """Find the configuration file for the site.

        Returns:
            str: Path to config file, or None if not found
        """
        site_path = self.siteinfo.site_path

        # Look for *-config.php files first (WordOps pattern)
        configs = glob.glob(os.path.join(site_path, '*-config.php'))
        if configs:
            return configs[0]

        # Look for wp-config.php in htdocs (WordPress standard)
        wp_config = os.path.join(site_path, 'htdocs', 'wp-config.php')
        if os.path.isfile(wp_config):
            return wp_config

        return None

    def _save_metadata(
        self,
        target_dir: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Collect and save backup metadata.

        Args:
            target_dir: Directory to save metadata
            extra: Additional metadata fields

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Collect standard site metadata
            metadata = collect_site_metadata(
                self.controller, self.siteinfo, self.site_name
            )

            # Add timestamp if not already provided
            if not extra or 'timestamp' not in extra:
                metadata['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')

            # Merge extra metadata if provided
            if extra:
                metadata.update(extra)

            # Save to vhost.json
            metadata_file = os.path.join(target_dir, 'vhost.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, default=str, indent=2)

            Log.debug(self.controller, f"Saved metadata to {metadata_file}")
            return True

        except Exception as e:
            Log.warn(self.controller, f'Failed to save metadata: {str(e)}')
            return False

    @staticmethod
    def list_backups(backup_root: str, site_name: str) -> list:
        """List all available backups for a site.

        Args:
            backup_root: Root backup directory
            site_name: Name of the site

        Returns:
            List of backup archive paths, sorted by timestamp (newest first)
        """
        domain_dir = os.path.join(backup_root, site_name)
        if not os.path.isdir(domain_dir):
            return []

        archives = glob.glob(os.path.join(domain_dir, '*.tar.zst'))
        # Sort by modification time, newest first
        archives.sort(key=os.path.getmtime, reverse=True)
        return archives

    @staticmethod
    def get_backup_info(archive_path: str) -> Optional[Dict[str, Any]]:
        """Extract metadata from a backup archive.

        Args:
            archive_path: Path to backup archive

        Returns:
            Dict with backup metadata, or None if extraction fails
        """
        if not os.path.isfile(archive_path):
            return None

        # Extract vhost.json from archive
        try:
            import subprocess
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                # List archive contents to find vhost.json
                list_cmd = ['tar', '--zstd', '-tf', archive_path]
                result = subprocess.run(
                    list_cmd, capture_output=True, text=True, check=True
                )

                # Find vhost.json in archive
                vhost_path = None
                for line in result.stdout.split('\n'):
                    if line.endswith('vhost.json'):
                        vhost_path = line
                        break

                if not vhost_path:
                    return None

                # Extract vhost.json
                extract_cmd = [
                    'tar', '--zstd', '-xf', archive_path,
                    '-C', tmpdir, vhost_path
                ]
                subprocess.run(extract_cmd, check=True)

                # Read metadata
                metadata_file = os.path.join(tmpdir, vhost_path)
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                # Add archive info
                metadata['archive_path'] = archive_path
                metadata['archive_size'] = os.path.getsize(archive_path)
                metadata['archive_mtime'] = os.path.getmtime(archive_path)

                return metadata

        except Exception:
            return None
