import json
import os
import tempfile

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import (
    check_domain_exists,
    pre_run_checks,
    setupdomain,
    setup_php_fpm,
    setwebrootpermissions,
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

    def _extract_backup(self, path):
        if os.path.isdir(path):
            return path
        tmpdir = tempfile.mkdtemp(prefix='wo-restore-')
        try:
            WOShellExec.cmd_exec(self, f'tar --zstd -xf {path} -C {tmpdir}')
        except CommandExecutionError as e:
            Log.debug(self, str(e))
            Log.error(self, 'failed to extract backup archive')
        entries = os.listdir(tmpdir)
        if not entries:
            Log.error(self, 'invalid backup archive')
        return os.path.join(tmpdir, entries[0])

    def _restore_db(self, dump_file, meta):
        db_name = meta.get('db_name')
        db_user = meta.get('db_user')
        db_pass = meta.get('db_password')
        db_host = meta.get('db_host', 'localhost')
        if not db_name or not os.path.isfile(dump_file):
            return
        try:
            WOMysql.execute(self, f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            if db_user:
                WOMysql.execute(
                    self,
                    f"CREATE USER IF NOT EXISTS `{db_user}`@`{db_host}` IDENTIFIED BY '{db_pass}'",
                    log=False,
                )
                WOMysql.execute(
                    self,
                    f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{db_user}`@`{db_host}`",
                    log=False,
                )
            WOShellExec.cmd_exec(self, f'mariadb {db_name} < {dump_file}', log=False)
        except (MySQLConnectionError, StatementExcecutionError, CommandExecutionError) as e:
            Log.debug(self, str(e))
            Log.warn(self, 'Failed to restore database')

    def _setup_letsencrypt(self, domain, webroot):
        (domain_type, _) = WODomain.getlevel(self, domain)
        parts = domain.split('.')
        if domain_type == 'subdomain' or (domain_type == '' and len(parts) > 2):
            acme_domains = [domain]
        else:
            acme_domains = [domain, f"www.{domain}"]
        acmedata = dict(dns=False, acme_dns='dns_cf',
                        dnsalias=False, acme_alias='', keylength='')
        if self.app.config.has_section('letsencrypt'):
            acmedata['keylength'] = self.app.config.get('letsencrypt',
                                                        'keylength')
        else:
            acmedata['keylength'] = 'ec-384'
        if WOAcme.setupletsencrypt(self, acme_domains, acmedata):
            WOAcme.deploycert(self, domain)
            SSL.httpsredirect(self, domain, acme_domains, True)
            SSL.siteurlhttps(self, domain)
            if not WOService.reload_service(self, 'nginx'):
                Log.error(self, 'service nginx reload failed. '
                          'check issues with `nginx -t` command')
            WOGit.add(self, [f"{webroot}/conf/nginx"],
                      msg=f"Adding letsencrypts config of site: {domain}")
            updateSiteInfo(self, domain, ssl=True)
            Log.info(self, f"Congratulations! Successfully Configured SSL on "
                     f"https://{domain}")

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        if not pargs.backup:
            pargs.backup = input('Enter path to backup : ').strip()
        backup_dir = self._extract_backup(pargs.backup)

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

        setup_php_fpm(self, data)
        setwebrootpermissions(self, site_path, data['php_fpm_user'])
        WOService.reload_service(self, 'nginx')

        src_root = os.path.join(backup_dir, 'htdocs')
        if os.path.isdir(src_root):
            dest_root = os.path.join(site_path, 'htdocs')
            WOFileUtils.rm(self, dest_root)
            WOFileUtils.copyfiles(self, src_root, dest_root)

        configs = [f for f in os.listdir(backup_dir) if f.endswith('-config.php') or f == 'wp-config.php']
        if configs:
            cfg_src = os.path.join(backup_dir, configs[0])
            cfg_dest = os.path.join(site_path, os.path.basename(cfg_src))
            WOFileUtils.copyfile(self, cfg_src, cfg_dest)

        dump_file = os.path.join(backup_dir, f'{site}.sql')
        self._restore_db(dump_file, meta)

        http_user = meta.get('httpauth_user')
        http_pass = meta.get('httpauth_pass')
        if http_user and http_pass:
            slug = site.replace('.', '-').lower()
            acl_dir = f'/etc/nginx/acl/{slug}'
            os.makedirs(acl_dir, exist_ok=True)
            protected = os.path.join(acl_dir, 'protected.conf')
            credentials = os.path.join(acl_dir, 'credentials')
            with open(credentials, 'w') as cred_file:
                cred_file.write(f"{http_user}:{http_pass}\n")
            pdata = {
                'slug': slug,
                'secure': True,
                'wp': 'wp' in site_type,
                'php_ver': php_version.replace('.', ''),
                'pool_name': slug,
            }
            WOTemplate.deploy(self, protected, 'protected.mustache', pdata, overwrite=True)
            WOGit.add(self, ['/etc/nginx'], msg=f"Secured {site} with basic auth")
            if not WOService.reload_service(self, 'nginx'):
                Log.error(self, "service nginx reload failed. check `nginx -t`")
            Log.info(self, f"Successfully secured {site}")

        if meta.get('is_ssl'):
            self._setup_letsencrypt(site, site_path)

        Log.info(self, f'Restored {site}')

