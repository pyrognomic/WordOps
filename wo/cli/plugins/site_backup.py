import json
import os
import glob
from datetime import datetime

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import SiteError, check_domain_exists
from wo.cli.plugins.sitedb import getSiteInfo, getAllsites
from wo.core.backup import WOBackup
from wo.core.domainvalidate import WODomain
from wo.core.logging import Log
from wo.core.fileutils import WOFileUtils


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
        """Backup a single site using the centralized backup service.

        Args:
            site: Site name to backup
            backup_root: Optional custom backup directory
            backup_db: Whether to backup database
            backup_files: Whether to backup files

        Returns:
            bool: True if backup was successful, False otherwise
        """
        # Get site information
        siteinfo = getSiteInfo(self, site)
        if not siteinfo:
            raise SiteError(f"Site {site} does not exist")

        # Determine backup type based on flags
        if backup_db and backup_files:
            backup_type = WOBackup.TYPE_FULL
        elif backup_db:
            backup_type = WOBackup.TYPE_DATABASE
        elif backup_files:
            backup_type = WOBackup.TYPE_FILES
        else:
            Log.warn(self, "No backup type selected (both --db and --files are False)")
            return False

        # Create backup using centralized service
        backup_service = WOBackup(self, siteinfo)
        success, archive = backup_service.create(
            backup_type=backup_type,
            backup_root=backup_root,
            metadata_extra={
                'backup_type': 'manual',
                'backup_flags': {
                    'database': backup_db,
                    'files': backup_files
                }
            }
        )

        if success:
            Log.info(self, f"Backup completed successfully for {site}")
            Log.info(self, f"Archive: {archive}")
        else:
            Log.warn(self, f"Backup completed with errors for {site}")

        return success

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
