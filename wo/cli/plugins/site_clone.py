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
            (['--new'], dict(help='do not copy wp-config from source', action='store_true')),
            (['--user'], dict(help='WordPress admin user')),
            (['--email'], dict(help='WordPress admin email')),
            (['--pass'], dict(help='WordPress admin password', dest='wppass')),
        ]

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
        data = dict(site_name=dest, www_domain=f"www.{dest}", webroot=dest_webroot,
                    static=False, basic=True, wp=False, wpfc=False, wpsc=False,
                    wprocket=False, wpce=False, wpredis=False,
                    multisite=False, wpsubdir=False, wo_php=php_key,
                    **{'wp-user': wpuser, 'wp-email': wpemail, 'wp-pass': wppass})
        data['pool_name'] = dest.replace('.', '-').lower()
        data['php_ver'] = php_key.replace('php', '')
        data['php_fpm_user'] = f"php-{data['pool_name']}"

        stype = src_info.site_type
        cache = src_info.cache_type if src_info.cache_type else 'basic'

        if stype in ['wp', 'wpsubdir', 'wpsubdomain']:
            data['wp'] = True
            data['basic'] = False
            data[cache] = True if cache != 'basic' else False
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
        setupwordpress(self, data, vhostonly=True)
        updateSiteInfo(self, dest, db_name=data['wo_db_name'],
                       db_user=data['wo_db_user'],
                       db_password=data['wo_db_pass'],
                       db_host=data['wo_db_host'],
                       php_version=src_info.php_version,
                       stype=stype, cache=cache)
        setup_php_fpm(self, data)
        setwebrootpermissions(self, dest_webroot, data['php_fpm_user'])
        WOService.reload_service(self, 'nginx')

        conf_src = os.path.join(WOVar.wo_webroot, src, 'wp-config.php')
        conf_dest = os.path.join(WOVar.wo_webroot, dest, 'wp-config.php')
        src_db = _parse_db_config(conf_src)
        dest_db = _parse_db_config(conf_dest)

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
        WOFileUtils.rm(self, dest_root)
        WOFileUtils.copyfiles(self, src_root.rstrip('/'), dest_root.rstrip('/'))
        WOShellExec.cmd_exec(
            self,
            f"{WOVar.wo_wpcli_path} search-replace {src} {dest} --path={dest_root} --all-tables --allow-root",
        )
        setwebrootpermissions(self, dest_root.rstrip('/'), data['php_fpm_user'])

        if not pargs.new:
            WOFileUtils.copyfile(self, conf_src, conf_dest)
            with open(conf_dest, 'r') as f:
                content = f.read()
            content = re.sub(r"define\('DB_NAME',\s*'[^']*'\)",
                             f"define('DB_NAME', '{dest_db['DB_NAME']}')", content)
            content = re.sub(r"define\('DB_USER',\s*'[^']*'\)",
                             f"define('DB_USER', '{dest_db['DB_USER']}')", content)
            content = re.sub(r"define\('DB_PASSWORD',\s*'[^']*'\)",
                             f"define('DB_PASSWORD', '{dest_db['DB_PASSWORD']}')", content)
            content = re.sub(r"define\('DB_HOST',\s*'[^']*'\)",
                             f"define('DB_HOST', '{dest_db['DB_HOST']}')", content)
            with open(conf_dest, 'w') as f:
                f.write(content)
            WOFileUtils.chown(self, conf_dest, WOVar.wo_php_user, WOVar.wo_php_user)

        WOFileUtils.rm(self, backup)
        Log.info(self, f"Successfully cloned '{src}' → '{dest}'")
