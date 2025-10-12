import json
import os
import glob
import shutil
from datetime import datetime

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import (
    SiteError, check_domain_exists, create_database_backup,
    collect_site_metadata, create_site_archive
)
from wo.cli.plugins.sitedb import getSiteInfo, getAllsites
from wo.core.domainvalidate import WODomain
from wo.core.logging import Log
from wo.core.fileutils import WOFileUtils
from wo.core.shellexec import WOShellExec, CommandExecutionError


def _timestamp():
    return datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')


class WOSiteBackupController(CementBaseController):
    class Meta:
        label = 'backup'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = ('this commands allow you to backup your sites')
        arguments = [
            (['site_name'],
             dict(help='domain name for the site to be backed up.', nargs='?')),
            (['--db'],
             dict(help='backup only site database', action='store_true')),
            (['--files'],
             dict(help='backup only site files', action='store_true')),
            (['--path'],
             dict(help='directory to store backups')),
            (['--all'],
             dict(help='backup all sites', action='store_true')),
            (['--remote'],
             dict(help='upload archive to an rclone destination (e.g. remote:path)', dest='remote')),
            (['--remote-retain'],
             dict(help='retain only the most recent N archives on the rclone destination',
                  type=int, dest='remote_retain')),
        ]

    def _backup_site(self, site, backup_root=None, backup_db=True, backup_files=True,
                     remote_destination=None, remote_retain=None):
        """Backup a single site with improved error handling."""
        # Get site information
        siteinfo = getSiteInfo(self, site)
        if not siteinfo:
            raise SiteError(f"Site {site} does not exist")

        # Setup backup directories
        timestamp = _timestamp()
        root = backup_root if backup_root else os.path.join(siteinfo.site_path, 'backup')
        domain_dir = os.path.join(root, site)
        target_dir = os.path.join(domain_dir, timestamp)
        WOFileUtils.mkdir(self, target_dir)

        backup_success = True

        # Backup files if requested
        if backup_files:
            if not self._backup_site_files(siteinfo, target_dir):
                backup_success = False

        # Backup database if requested
        if backup_db:
            if not create_database_backup(self, siteinfo, target_dir, site):
                backup_success = False

        # Collect and save metadata
        metadata = collect_site_metadata(self, siteinfo, site)
        try:
            with open(os.path.join(target_dir, 'vhost.json'), 'w') as f:
                json.dump(metadata, f, default=str, indent=2)
        except OSError as e:
            Log.warn(self, f'Failed to save metadata: {str(e)}')
            backup_success = False

        archive_path = os.path.join(domain_dir, f'{timestamp}.tar.zst')

        # Create archive
        if backup_success:
            if not create_site_archive(self, domain_dir, timestamp):
                backup_success = False
            elif remote_destination:
                if not self._upload_with_rclone(archive_path, remote_destination):
                    backup_success = False
                elif remote_retain and remote_retain > 0:
                    self._prune_remote_backups(remote_destination, remote_retain)

        if backup_success:
            Log.info(self, f"Backup completed successfully for {site}")
        else:
            Log.warn(self, f"Backup completed with some errors for {site}")

        return backup_success

    def _backup_site_files(self, siteinfo, target_dir):
        """Backup site files (htdocs and config)."""
        # Backup htdocs directory
        src = os.path.join(siteinfo.site_path, 'htdocs')
        if os.path.isdir(src):
            try:
                WOFileUtils.copyfiles(self, src, os.path.join(target_dir, 'htdocs'))
            except Exception as e:
                Log.warn(self, f'Failed to backup htdocs: {str(e)}')
                return False

        # Backup configuration files
        config_file = self._find_config_file(siteinfo.site_path)
        if config_file:
            try:
                WOFileUtils.copyfile(self, config_file,
                                    os.path.join(target_dir, os.path.basename(config_file)))
            except Exception as e:
                Log.warn(self, f'Failed to backup config file: {str(e)}')
                return False

        return True

    def _find_config_file(self, site_path):
        """Find the configuration file for a site."""
        # Look for *-config.php files first
        configs = glob.glob(os.path.join(site_path, '*-config.php'))
        if configs:
            return configs[0]

        # Look for wp-config.php in htdocs
        wp_cfg = os.path.join(site_path, 'htdocs', 'wp-config.php')
        if os.path.isfile(wp_cfg):
            return wp_cfg

        return None

    def _normalize_remote_dir(self, remote_destination):
        if not remote_destination:
            return None
        remote_dir = remote_destination.strip().rstrip('/')
        return remote_dir

    def _build_remote_file_path(self, remote_dir, filename):
        if remote_dir.endswith(':'):
            return f'{remote_dir}{filename}'
        return f'{remote_dir}/{filename}'

    def _upload_with_rclone(self, archive_path, remote_destination):
        remote_dir = self._normalize_remote_dir(remote_destination)
        if not remote_dir:
            Log.warn(self, 'No remote destination provided for rclone upload')
            return False

        archive_name = os.path.basename(archive_path)
        remote_file = self._build_remote_file_path(remote_dir, archive_name)

        try:
            if not WOShellExec.cmd_exec(self, ['rclone', 'mkdir', remote_dir]):
                Log.warn(self, f'Failed to ensure remote directory exists: {remote_dir}')
                return False
        except CommandExecutionError:
            Log.warn(self, f'Failed to ensure remote directory exists: {remote_dir}')
            return False

        try:
            if WOShellExec.cmd_exec(
                self,
                ['rclone', 'copyto', archive_path, remote_file],
                errormsg='Failed to upload backup archive with rclone',
            ):
                Log.info(self, f'Uploaded backup to {remote_file}')
                return True
            Log.warn(self, 'Failed to upload backup archive with rclone')
            return False
        except CommandExecutionError:
            Log.warn(self, 'Failed to upload backup archive with rclone')
            return False

    def _prune_remote_backups(self, remote_destination, retain):
        if retain < 1:
            return

        remote_dir = self._normalize_remote_dir(remote_destination)
        if not remote_dir:
            return

        try:
            output = WOShellExec.cmd_exec_stdout(
                self,
                ['rclone', 'lsjson', remote_dir],
                errormsg=f'Unable to list remote backups at {remote_dir}',
            )
        except CommandExecutionError:
            Log.warn(self, f'Unable to list remote backups at {remote_dir}')
            return

        try:
            entries = json.loads(output) if output else []
        except json.JSONDecodeError:
            Log.warn(self, f'Unable to parse remote backup listing from {remote_dir}')
            return

        files = [entry for entry in entries if not entry.get('IsDir') and entry.get('Name')]
        if len(files) <= retain:
            return

        files.sort(key=lambda item: item.get('Name'))
        to_delete = files[:-retain]
        for entry in to_delete:
            remote_file = self._build_remote_file_path(remote_dir, entry['Name'])
            if WOShellExec.cmd_exec(
                self,
                ['rclone', 'deletefile', remote_file],
                errormsg=f'Failed to delete remote backup {remote_file}',
            ):
                Log.info(self, f'Removed remote backup {remote_file}')
            else:
                Log.warn(self, f'Failed to delete remote backup {remote_file}')
                break

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs

        if getattr(pargs, 'remote_retain', None) is not None and not getattr(pargs, 'remote', None):
            Log.error(self, "--remote-retain requires --remote to be set")
            return

        if getattr(pargs, 'remote', None):
            if shutil.which('rclone') is None:
                Log.error(self, "rclone binary not found. Install rclone or remove the --remote option.")
                return
            if getattr(pargs, 'remote_retain', None) is not None and pargs.remote_retain < 1:
                Log.error(self, "--remote-retain must be a positive integer")
                return

        backup_db = True
        backup_files = True
        if pargs.db and not pargs.files:
            backup_files = False
        if pargs.files and not pargs.db:
            backup_db = False

        if pargs.all:
            if pargs.site_name:
                Log.error(self, '`--all` option cannot be used with site name provided')
            sites = getAllsites(self)
            if not sites:
                Log.info(self, "No sites found to backup")
                return

            success_count = 0
            for site in sites:
                try:
                    if self._backup_site(
                        site.sitename,
                        backup_root=pargs.path,
                        backup_db=backup_db,
                        backup_files=backup_files,
                        remote_destination=pargs.remote,
                        remote_retain=pargs.remote_retain,
                    ):
                        success_count += 1
                except SiteError as e:
                    Log.error(self, f"Site {site.sitename}: {str(e)}")
                except Exception as e:
                    Log.error(self, f"Unexpected error backing up {site.sitename}: {str(e)}")
                    Log.debug(self, f"Backup error details: {str(e)}")

            Log.info(self, f"Backup completed for {success_count}/{len(sites)} sites")
            return

        if not pargs.site_name:
            try:
                while not pargs.site_name:
                    pargs.site_name = input('Enter site name : ').strip()
            except IOError as e:
                Log.debug(self, str(e))
                Log.error(self, 'Unable to input site name, Please try again!')

        pargs.site_name = pargs.site_name.strip()
        wo_domain = WODomain.validate(self, pargs.site_name)
        if not check_domain_exists(self, wo_domain):
            Log.error(self, f"site {wo_domain} does not exist")

        try:
            success = self._backup_site(
                wo_domain,
                backup_root=pargs.path,
                backup_db=backup_db,
                backup_files=backup_files,
                remote_destination=pargs.remote,
                remote_retain=pargs.remote_retain,
            )
            if not success:
                Log.error(self, f"Backup failed for {wo_domain}")
        except SiteError as e:
            Log.error(self, str(e))
        except Exception as e:
            Log.error(self, f"Unexpected error during backup: {str(e)}")
            Log.debug(self, f"Backup error details: {str(e)}")
