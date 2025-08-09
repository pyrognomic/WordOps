import json
import os

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.sitedb import addNewSite
from wo.cli.plugins.site_functions import SiteError, setup_php_fpm, setupdomain
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.mysql import (MySQLConnectionError, StatementExcecutionError,
                           WOMysql)
from wo.core.shellexec import CommandExecutionError, WOShellExec


class WOSiteRestoreController(CementBaseController):
    class Meta:
        label = 'restore'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = ('restore sites from a backup directory')
        arguments = [
            (['backup_path'],
             dict(help='path to directory containing vhost backups', nargs='?')),
        ]

    def _restore_vhost(self, vhost_dir):
        """Restore a single vhost from its backup directory."""
        meta_file = os.path.join(vhost_dir, 'vhost.json')
        if not os.path.isfile(meta_file):
            Log.debug(self, f'Skipping {vhost_dir}, vhost.json not found')
            return

        with open(meta_file, 'r') as f:
            meta = json.load(f)

        site_name = meta.get('sitename')
        if not site_name:
            Log.debug(self, f'Missing sitename in {meta_file}')
            return

        site_path = meta.get('site_path', f'/var/www/{site_name}')
        site_type = meta.get('site_type', 'html')
        cache_type = meta.get('cache_type', 'basic')
        php_version = meta.get('php_version', '8.1')
        db_name = meta.get('db_name')
        db_user = meta.get('db_user')
        db_password = meta.get('db_password')
        db_host = meta.get('db_host', 'localhost')
        is_ssl = meta.get('is_ssl', False)
        is_enabled = meta.get('is_enabled', True)
        fs = meta.get('storage_fs', 'ext4')
        db = meta.get('storage_db', 'mysql')
        is_hhvm = meta.get('is_hhvm')

        slug = site_name.replace('.', '-')
        php_key = f"php{php_version.replace('.', '')}"
        php_ver_short = php_version.replace('.', '')

        # prepare data for domain and php-fpm setup
        data = {
            'site_name': site_name,
            'www_domain': f'www.{site_name}',
            'webroot': site_path,
            'static': site_type == 'html',
            'basic': cache_type == 'basic',
            'wp': site_type in ['wp', 'wpsubdir', 'wpsubdomain'],
            'wpfc': cache_type == 'wpfc',
            'wpsc': cache_type == 'wpsc',
            'wprocket': cache_type == 'wprocket',
            'wpce': cache_type == 'wpce',
            'multisite': site_type in ['wpsubdir', 'wpsubdomain'],
            'wpsubdir': site_type == 'wpsubdir',
            'php_ver': php_ver_short,
            'wo_php': php_key,
            'pool_name': slug,
            'php_fpm_user': f'php-{slug}',
        }

        # generate nginx configuration and webroot structure
        try:
            setupdomain(self, data)
        except SiteError as e:
            Log.debug(self, str(e))
            Log.error(self, f'Failed to setup domain for {site_name}')
            return

        # restore original nginx configuration if present
        nginx_conf = os.path.join(vhost_dir, site_name)
        if os.path.exists(nginx_conf):
            dest_conf = f'/etc/nginx/sites-available/{site_name}'
            WOFileUtils.copyfile(self, nginx_conf, dest_conf)

        # configure php-fpm pool
        try:
            setup_php_fpm(self, data)
        except SiteError as e:
            Log.debug(self, str(e))
            Log.warn(self, f'Failed to configure php-fpm for {site_name}')

        # ensure site enabled symlink
        dest_conf = f'/etc/nginx/sites-available/{site_name}'
        WOFileUtils.create_symlink(self, [dest_conf, f'/etc/nginx/sites-enabled/{site_name}'])

        # Restore webroot if present
        htdocs_src = os.path.join(vhost_dir, 'htdocs')
        if os.path.isdir(htdocs_src):
            dest_root = os.path.join(site_path, 'htdocs')
            WOFileUtils.copyfiles(self, htdocs_src, dest_root)

        # Restore database from dump when available
        dump_file = os.path.join(vhost_dir, f'{db_name}.zst') if db_name else None
        if dump_file and os.path.isfile(dump_file):
            try:
                WOMysql.execute(self, f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
                if db_user:
                    WOMysql.execute(
                        self,
                        f"CREATE USER IF NOT EXISTS `{db_user}`@`{db_host}` IDENTIFIED BY '{db_password}'",
                        log=False,
                    )
                    WOMysql.execute(
                        self,
                        f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{db_user}`@`{db_host}`",
                        log=False,
                    )
                WOShellExec.cmd_exec(
                    self, f'zstd -dc {dump_file} | mysql {db_name}', log=False)
            except (MySQLConnectionError, StatementExcecutionError,
                    CommandExecutionError) as e:
                Log.debug(self, str(e))
                Log.warn(self, f'Failed to restore database for {site_name}')

        # Add entry to the WordOps database
        addNewSite(
            self,
            site_name,
            site_type,
            cache_type,
            site_path,
            enabled=is_enabled,
            ssl=is_ssl,
            fs=fs,
            db=db,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            db_host=db_host,
            hhvm=is_hhvm,
            php_version=php_version,
        )

        Log.info(self, f'Restored {site_name}')

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        backup_root = pargs.backup_path if pargs.backup_path else os.getcwd()
        if not os.path.isdir(backup_root):
            Log.error(self, f'Backup path {backup_root} does not exist')

        for entry in os.listdir(backup_root):
            vhost_dir = os.path.join(backup_root, entry)
            if os.path.isdir(vhost_dir):
                try:
                    self._restore_vhost(vhost_dir)
                except Exception as e:
                    Log.debug(self, str(e))
                    Log.error(self, f'Failed to restore {entry}')


def load(app):
    app.handler.register(WOSiteRestoreController)
