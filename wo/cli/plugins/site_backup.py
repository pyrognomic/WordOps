import json
import os
import glob
from datetime import datetime

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import SiteError, check_domain_exists
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
        siteinfo = getSiteInfo(self, site)
        if not siteinfo:
            Log.error(self, f"Site {site} does not exist")

        timestamp = _timestamp()
        root = backup_root if backup_root else os.path.join(siteinfo.site_path, 'backup')
        domain_dir = os.path.join(root, site)
        target_dir = os.path.join(domain_dir, timestamp)
        WOFileUtils.mkdir(self, target_dir)

        if backup_files:
            src = os.path.join(siteinfo.site_path, 'htdocs')
            if os.path.isdir(src):
                WOFileUtils.copyfiles(self, src, os.path.join(target_dir, 'htdocs'))

        config_file = None
        configs = glob.glob(os.path.join(siteinfo.site_path, '*-config.php'))
        if configs:
            config_file = configs[0]
        else:
            wp_cfg = os.path.join(siteinfo.site_path, 'htdocs', 'wp-config.php')
            if os.path.isfile(wp_cfg):
                config_file = wp_cfg
        if config_file:
            WOFileUtils.copyfile(self, config_file, os.path.join(target_dir, os.path.basename(config_file)))

        if backup_db and siteinfo.db_name:
            dump_file = os.path.join(target_dir, f'{site}.sql')
            try:
                cmd = (
                    f"mysqldump --single-transaction --hex-blob {siteinfo.db_name} > {dump_file}"
                )
                if not WOShellExec.cmd_exec(self, cmd):
                    raise SiteError('mysqldump failed')
            except (CommandExecutionError, SiteError) as e:
                Log.debug(self, str(e))
                Log.warn(self, 'Failed to backup database')

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
            except OSError as e:
                Log.debug(self, str(e))

        with open(os.path.join(target_dir, 'vhost.json'), 'w') as f:
            json.dump(metadata, f, default=str, indent=2)

        archive = os.path.join(domain_dir, f'{timestamp}.tar.zst')
        try:
            if WOShellExec.cmd_exec(
                self,
                f"tar --zstd -cf {archive} -C {domain_dir} {timestamp}",
            ):
                WOFileUtils.remove(self, [target_dir])
            else:
                Log.warn(self, 'Failed to create archive')
        except CommandExecutionError as e:
            Log.debug(self, str(e))
            Log.warn(self, 'Failed to create archive')

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
                return
            for site in sites:
                try:
                    self._backup_site(
                        site.sitename,
                        backup_root=pargs.path,
                        backup_db=backup_db,
                        backup_files=backup_files,
                    )
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
            self._backup_site(
                wo_domain,
                backup_root=pargs.path,
                backup_db=backup_db,
                backup_files=backup_files,
            )
        except Exception as e:
            Log.debug(self, str(e))
