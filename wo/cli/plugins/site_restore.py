import json
import os
import tempfile

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import (
    check_domain_exists,
    pre_run_checks,
    setupdomain,
    setup_php_fpm,
    setup_letsencrypt,
    setwebrootpermissions,
    extract_site_backup,
    restore_database_from_dump,
)
from wo.cli.plugins.sitedb import addNewSite, updateSiteInfo
from wo.core.domainvalidate import WODomain
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.mysql import (
    MySQLConnectionError,
    StatementExcecutionError,
    WOMysql,
)
from wo.core.nginxhashbucket import hashbucket
from wo.core.shellexec import CommandExecutionError, WOShellExec
from wo.core.services import WOService
from wo.core.template import WOTemplate
from wo.core.git import WOGit
from wo.core.acme import WOAcme
from wo.core.sslutils import SSL


class WOSiteRestoreController(CementBaseController):
    class Meta:
        label = 'restore'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = 'restore site from backup'
        arguments = [
            (['backup'], dict(help='path to backup archive or directory', nargs='?')),
        ]

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        if not pargs.backup:
            pargs.backup = input('Enter path to backup : ').strip()
        backup_dir = extract_site_backup(self, pargs.backup)

        meta_file = os.path.join(backup_dir, 'vhost.json')
        if not os.path.isfile(meta_file):
            Log.error(self, 'vhost.json not found in backup')
        with open(meta_file) as f:
            meta = json.load(f)

        site = meta.get('sitename')
        if not site:
            Log.error(self, 'invalid metadata: missing sitename')
        if check_domain_exists(self, site):
            Log.error(self, f'site {site} already exists')

        site_path = meta.get('site_path', os.path.join('/var/www', site))
        site_type = meta.get('site_type', 'html')
        cache_type = meta.get('cache_type', 'basic')
        php_version = meta.get('php_version', '8.1')

        (domain_type, _) = WODomain.getlevel(self, site)
        www_domain = f'www.{site}' if domain_type != 'subdomain' else ''
        slug = site.replace('.', '-').lower()
        php_key = f"php{php_version.replace('.', '')}"
        data = {
            'site_name': site,
            'www_domain': www_domain,
            'webroot': site_path,
            'static': site_type == 'html',
            'basic': cache_type == 'basic',
            'wp': site_type in ['wp', 'wpsubdir', 'wpsubdomain'],
            'wpfc': cache_type == 'wpfc',
            'wpsc': cache_type == 'wpsc',
            'wprocket': cache_type == 'wprocket',
            'wpce': cache_type == 'wpce',
            'wpredis': cache_type == 'wpredis',
            'multisite': site_type in ['wpsubdir', 'wpsubdomain'],
            'wpsubdir': site_type == 'wpsubdir',
            'wo_php': php_key,
            'php_ver': php_key.replace('php', ''),
            'pool_name': slug,
            'php_fpm_user': f'php-{slug}',
        }

        pre_run_checks(self)
        setupdomain(self, data)
        hashbucket(self)

        addNewSite(
            self,
            site,
            site_type,
            cache_type,
            site_path,
            enabled=meta.get('is_enabled', True),
            ssl=meta.get('is_ssl', False),
            fs=meta.get('storage_fs', 'ext4'),
            db=meta.get('storage_db', 'mysql'),
            db_name=meta.get('db_name'),
            db_user=meta.get('db_user'),
            db_password=meta.get('db_password'),
            db_host=meta.get('db_host', 'localhost'),
            hhvm=meta.get('is_hhvm'),
            php_version=php_version,
        )

        # setup wp-login.php protection if exists
        slug = site.replace('.', '-').lower()
        acl_dir = f'/etc/nginx/acl/{slug}'
        os.makedirs(acl_dir, exist_ok=True)

        protected = os.path.join(acl_dir, 'protected.conf')
        open(protected, 'w').close()

        credentials = os.path.join(acl_dir, 'credentials')
        open(credentials, 'w').close()

        pdata = {
            'slug': slug,
            'secure': False,
            'wp': 'wp' in site_type,
            'php_ver': php_version.replace('.', ''),
            'pool_name': slug,
        }

        http_user = meta.get('httpauth_user')
        http_pass = meta.get('httpauth_pass')
        if http_user and http_pass:
            pdata['secure'] = True
            with open(credentials, 'w') as cred_file:
                cred_file.write(f"{http_user}:{http_pass}\n")

        WOTemplate.deploy(self, protected, 'protected.mustache', pdata, overwrite=True)

        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, "service nginx reload failed. check `nginx -t`")
        Log.info(self, f"Successfully secured {site}")

        setup_php_fpm(self, data)

        # Create safety backup before restoration
        existing_backup = None
        dest_root = os.path.join(site_path, 'htdocs')
        if os.path.exists(dest_root):
            try:
                import tempfile
                existing_backup = tempfile.mkdtemp(prefix='wo-restore-safety-')
                WOFileUtils.copyfiles(self, dest_root, os.path.join(existing_backup, 'htdocs'))
                Log.debug(self, f"Created safety backup at: {existing_backup}")
            except Exception as e:
                Log.debug(self, f"Warning: Could not create safety backup: {str(e)}")

        try:
            # Restore website files
            src_root = os.path.join(backup_dir, 'htdocs')
            if os.path.isdir(src_root):
                WOFileUtils.rm(self, dest_root)
                WOFileUtils.copyfiles(self, src_root, dest_root)
                Log.info(self, "Website files restored successfully")
            else:
                Log.warn(self, f"No htdocs directory found in backup: {src_root}")

            # Restore configuration files
            configs = [f for f in os.listdir(backup_dir) if f.endswith('-config.php') or f == 'wp-config.php']
            if configs:
                cfg_src = os.path.join(backup_dir, configs[0])
                cfg_dest = os.path.join(site_path, os.path.basename(cfg_src))
                WOFileUtils.copyfile(self, cfg_src, cfg_dest)
                Log.info(self, f"Configuration file restored: {os.path.basename(cfg_src)}")

            # Set proper permissions
            setwebrootpermissions(self, site_path, data['php_fpm_user'])

            # Reload nginx
            WOService.reload_service(self, 'nginx')

            # Restore database
            dump_file = os.path.join(backup_dir, f'{site}.sql')
            if os.path.exists(dump_file):
                restore_database_from_dump(self, dump_file, meta)
                Log.info(self, "Database restored successfully")
            else:
                Log.warn(self, f"No database dump found: {dump_file}")

            # Clean up safety backup on success
            if existing_backup and os.path.exists(existing_backup):
                import shutil
                shutil.rmtree(existing_backup)

        except Exception as e:
            Log.error(self, f"Restore failed: {str(e)}")

            # Attempt to restore from safety backup
            if existing_backup and os.path.exists(existing_backup):
                try:
                    safety_htdocs = os.path.join(existing_backup, 'htdocs')
                    if os.path.exists(safety_htdocs):
                        if os.path.exists(dest_root):
                            WOFileUtils.rm(self, dest_root)
                        WOFileUtils.copyfiles(self, safety_htdocs, dest_root)
                        Log.info(self, "Original files restored from safety backup")
                except Exception as rollback_error:
                    Log.error(self, f"Failed to rollback: {str(rollback_error)}")

            raise SiteError(f"Site restoration failed: {str(e)}")

        if meta.get('is_ssl'):
            setup_letsencrypt(self, site, site_path)

        Log.info(self, f'Restored {site}')

