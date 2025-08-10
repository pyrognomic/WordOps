import json
import os

from cement.core.controller import CementBaseController, expose
from wo.cli.plugins.site_functions import (
    SiteError,
    check_domain_exists,
    sitebackup,
)
from wo.cli.plugins.sitedb import getAllsites, getSiteInfo
from wo.core.domainvalidate import WODomain
from wo.core.logging import Log
from wo.core.variables import WOVar
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
            (['--all'],
             dict(help='backup all sites', action='store_true')),
        ]

    def _backup_site(self, site, db_only=False, files_only=False):
        """Backup single site using shared sitebackup helper."""
        siteinfo = getSiteInfo(self, site)
        if not siteinfo:
            Log.error(self, f"Site {site} does not exist")

        data = {
            'site_name': site,
            'webroot': siteinfo.site_path,
            'currsitetype': siteinfo.site_type,
            'wp': siteinfo.site_type in ['wp', 'wpsubdir', 'wpsubdomain'],
            'wo_db_name': siteinfo.db_name,
            'php73': siteinfo.php_version == '7.3'
        }

        try:
            sitebackup(
                self,
                data,
                move_files=False,
                db_only=db_only,
                files_only=files_only,
            )
            backup_path = os.path.join(siteinfo.site_path, 'backup', WOVar.wo_date)

            metadata = {
                'id': siteinfo.id,
                'sitename': siteinfo.sitename,
                'site_type': siteinfo.site_type,
                'cache_type': siteinfo.cache_type,
                'site_path': siteinfo.site_path,
                'created_on': siteinfo.created_on.isoformat() if siteinfo.created_on else None,
                'is_enabled': siteinfo.is_enabled,
                'is_ssl': siteinfo.is_ssl,
                'storage_fs': siteinfo.storage_fs,
                'storage_db': siteinfo.storage_db,
                'db_name': siteinfo.db_name,
                'db_user': siteinfo.db_user,
                'db_password': siteinfo.db_password,
                'db_host': siteinfo.db_host,
                'is_hhvm': siteinfo.is_hhvm,
                'php_version': siteinfo.php_version,
            }

            slug = site.replace('.', '-').lower()
            cred_file = f'/etc/nginx/acl/{slug}/credentials'
            if os.path.isfile(cred_file):
                try:
                    with open(cred_file) as cf:
                        cred_line = cf.readline().strip()
                    if ':' in cred_line:
                        user, passwd = cred_line.split(':', 1)
                        metadata['httpauth_user'] = user
                        metadata['httpauth_pass'] = passwd
                    WOFileUtils.copyfile(self, cred_file, backup_path)
                except OSError as e:
                    Log.debug(self, str(e))

            with open(os.path.join(backup_path, 'vhost.json'), 'w') as f:
                json.dump(metadata, f, default=str, indent=2)
        except (SiteError, OSError) as e:
            Log.debug(self, str(e))

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs

        if pargs.all:
            sites = [site.sitename for site in getAllsites(self)]
            for sitename in sites:
                try:
                    self._backup_site(sitename, db_only=pargs.db, files_only=pargs.files)
                except Exception as e:
                    Log.debug(self, str(e))
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
            self._backup_site(wo_domain, db_only=pargs.db, files_only=pargs.files)
        except Exception as e:
            Log.debug(self, str(e))
