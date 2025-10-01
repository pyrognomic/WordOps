import json
import os
import glob
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
        ]

    def _backup_site(self, site, backup_root=None, backup_db=True, backup_files=True):
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

        # Create archive
        if backup_success:
            if not create_site_archive(self, domain_dir, timestamp):
                backup_success = False

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

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs

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
            )
            if not success:
                Log.error(self, f"Backup failed for {wo_domain}")
        except SiteError as e:
            Log.error(self, str(e))
        except Exception as e:
            Log.error(self, f"Unexpected error during backup: {str(e)}")
            Log.debug(self, f"Backup error details: {str(e)}")
