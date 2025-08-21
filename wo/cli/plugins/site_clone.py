import os
import re
from getpass import getpass

from cement.core.controller import CementBaseController, expose
from wo.cli.plugins.site_functions import (
    check_domain_exists, pre_run_checks, setupdomain,
    setupdatabase, setupwordpress, setwebrootpermissions, setup_php_fpm)
from wo.cli.plugins.sitedb import addNewSite, updateSiteInfo, getSiteInfo
from wo.core.domainvalidate import WODomain
from wo.core.logging import Log
from wo.core.nginxhashbucket import hashbucket
from wo.core.services import WOService
from wo.core.variables import WOVar
from wo.core.shellexec import WOShellExec
from wo.core.fileutils import WOFileUtils
from wo.core.acme import WOAcme
from wo.core.sslutils import SSL
from wo.core.git import WOGit


def _parse_db_config(path):
    creds = {}
    if not os.path.isfile(path):
        return creds
    with open(path, 'r') as f:
        for line in f:
            if 'DB_NAME' in line:
                creds['DB_NAME'] = line.split("'")[3]
            elif 'DB_USER' in line:
                creds['DB_USER'] = line.split("'")[3]
            elif 'DB_PASSWORD' in line:
                creds['DB_PASSWORD'] = line.split("'")[3]
            elif 'DB_HOST' in line:
                creds['DB_HOST'] = line.split("'")[3]
    return creds


class WOSiteCloneController(CementBaseController):
    class Meta:
        label = 'clone'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = 'clone an existing site'
        arguments = [
            (['site_name'], dict(help='source site', nargs='?')),
            (['newsite_name'], dict(help='destination site', nargs='?')),
            (['--user'], dict(help='WordPress admin user')),
            (['--email'], dict(help='WordPress admin email')),
            (['--pass'], dict(help='WordPress admin password', dest='wppass')),
        ]

    def _copy_acl(self, src_slug, dest_slug, base='/etc/nginx/acl'):
        """Copy Nginx ACL files from src_slug to dest_slug."""
        src_acl = os.path.join(base, src_slug)
        dest_acl = os.path.join(base, dest_slug)
        if not os.path.isdir(src_acl):
            return
        os.makedirs(base, exist_ok=True)
        if os.path.exists(dest_acl):
            WOFileUtils.rm(self, dest_acl)
        WOFileUtils.copyfiles(self, src_acl, dest_acl)
        protected = os.path.join(dest_acl, 'protected.conf')
        if os.path.isfile(protected):
            with open(protected, 'r') as f:
                content = f.read()
            content = content.replace(src_slug, dest_slug)
            with open(protected, 'w') as f:
                f.write(content)

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
        if not pargs.site_name:
            pargs.site_name = input('Enter source site name : ').strip()
        if not pargs.newsite_name:
            pargs.newsite_name = input('Enter destination site name : ').strip()

        src = WODomain.validate(self, pargs.site_name.strip())
        dest = WODomain.validate(self, pargs.newsite_name.strip())

        if not check_domain_exists(self, src):
            Log.error(self, f"source site {src} does not exist")
        if check_domain_exists(self, dest):
            Log.error(self, f"destination site {dest} already exists")

        wpuser = pargs.user or WOVar.wo_user
        wpemail = pargs.email or WOVar.wo_email
        wppass = pargs.wppass or getpass(f"Enter admin password for {wpuser}: ")
        if not wppass:
            Log.error(self, 'password cannot be empty')

        dest_webroot = os.path.join(WOVar.wo_webroot, dest)

        src_info = getSiteInfo(self, src)
        if not src_info:
            Log.error(self, f"source site {src} does not exist")

        php_key = ("php" + src_info.php_version).replace('.', '')
        (dest_type, _) = WODomain.getlevel(self, dest)
        www_domain = f"www.{dest}" if dest_type != 'subdomain' else ''
        data = dict(site_name=dest, www_domain=www_domain, webroot=dest_webroot,
                    static=False, basic=True, wp=False, wpfc=False, wpsc=False,
                    wprocket=False, wpce=False, wpredis=False,
                    multisite=False, wpsubdir=False, wo_php=php_key,
                    **{'wp-user': wpuser, 'wp-email': wpemail, 'wp-pass': wppass})
        data['pool_name'] = dest.replace('.', '-').lower()
        data['php_ver'] = php_key.replace('php', '')
        data['php_fpm_user'] = f"php-{data['pool_name']}"

        stype = src_info.site_type
        cache = src_info.cache_type if src_info.cache_type else 'basic'

        if 'wp' in stype:
            data['wp'] = True
            data['basic'] = cache == 'basic'
            if cache != 'basic':
                data[cache] = True
            data['multisite'] = stype in ['wpsubdir', 'wpsubdomain']
            if stype == 'wpsubdir':
                data['wpsubdir'] = True
        elif stype.startswith('php') or stype == 'php':
            data['static'] = False
            data['basic'] = True
        else:
            data['static'] = True
            data['basic'] = False

        pre_run_checks(self)
        setupdomain(self, data)
        hashbucket(self)
        addNewSite(self, dest, stype, cache, dest_webroot,
                   php_version=src_info.php_version)
        data = setupdatabase(self, data)
        updateSiteInfo(self, dest, db_name=data['wo_db_name'],
                       db_user=data['wo_db_user'],
                       db_password=data['wo_db_pass'],
                       db_host=data['wo_db_host'],
                       php_version=src_info.php_version,
                       stype=stype, cache=cache)
        setup_php_fpm(self, data)

        src_slug = src.replace('.', '-').lower()
        dest_slug = dest.replace('.', '-').lower()
        self._copy_acl(src_slug, dest_slug)

        conf_src = os.path.join(WOVar.wo_webroot, src, 'wp-config.php')
        conf_dest = os.path.join(WOVar.wo_webroot, dest, 'wp-config.php')
        src_db = _parse_db_config(conf_src)
        dest_db = {
            'DB_NAME': data['wo_db_name'],
            'DB_USER': data['wo_db_user'],
            'DB_PASSWORD': data['wo_db_pass'],
            'DB_HOST': data['wo_db_host'],
        }

        backup = f"/tmp/{src.replace('.', '_')}.sql"
        dump_cmd = (
            f"mariadb-dump --defaults-extra-file=/etc/mysql/conf.d/my.cnf "
            f"--single-transaction --quick --add-drop-table --hex-blob {src_db['DB_NAME']} > {backup}"
        )
        WOShellExec.cmd_exec(self, dump_cmd)

        import_cmd = (
            f"mariadb --defaults-extra-file=/etc/mysql/conf.d/my.cnf {dest_db['DB_NAME']} < {backup}"
        )
        WOShellExec.cmd_exec(self, import_cmd)

        src_root = os.path.join(WOVar.wo_webroot, src, 'htdocs/')
        dest_root = os.path.join(WOVar.wo_webroot, dest, 'htdocs/')

        # generate new wp-config.php
        setupwordpress(self, data, vhostonly=True)

        WOFileUtils.rm(self, dest_root)
        WOFileUtils.copyfiles(self, src_root.rstrip('/'), dest_root.rstrip('/'))

        # change domain name
        WOShellExec.cmd_exec(
            self,
            f"{WOVar.wo_wpcli_path} search-replace {src} {dest} --path={dest_root} --all-tables --allow-root",
        )

        # set permissions for webroot and wp-config.php
        setwebrootpermissions(self, dest_root.rstrip('/'), data['php_fpm_user'])

        WOService.reload_service(self, 'nginx')

        WOFileUtils.rm(self, backup)
        if src_info.is_ssl:
            self._setup_letsencrypt(dest, dest_webroot)
        Log.info(self, f"Successfully cloned '{src}' → '{dest}'")
