import os

from cement.core.controller import CementBaseController, expose
from wo.cli.plugins.site_functions import (
    detSitePar, check_domain_exists, site_package_check,
    pre_run_checks, setupdomain, SiteError,
    doCleanupAction, setupdatabase, setupwordpress, setwebrootpermissions,
    setup_php_fpm, setup_letsencrypt_advanced,
    determine_site_type, handle_site_error_cleanup,
    display_cache_settings, copyWildcardCert, PHPVersionManager)
from wo.cli.plugins.sitedb import (addNewSite, deleteSiteInfo,
                                   updateSiteInfo, getSiteInfo)
from wo.core.acme import WOAcme
from wo.core.domainvalidate import WODomain
from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.nginxhashbucket import hashbucket
from wo.core.services import WOService
from wo.core.sslutils import SSL
from wo.core.template import WOTemplate
from wo.core.random import RANDOM
from wo.core.shellexec import WOShellExec
from wo.core.variables import WOVar


class WOSiteCreateController(CementBaseController):
    class Meta:
        label = 'create'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = ('this commands set up configuration and installs '
                       'required files as options are provided')
        arguments = [
            (['site_name'],
                dict(help='domain name for the site to be created.',
                     nargs='?')),
            (['--html'],
                dict(help="create html site", action='store_true')),
            (['--php'],
             dict(help="create php site", action='store_true')),
            (['--mysql'],
                dict(help="create mysql site", action='store_true')),
            (['--wp'],
                dict(help="create WordPress single site",
                     action='store_true')),
            (['--wpsubdir'],
                dict(help="create WordPress multisite with subdirectory setup",
                     action='store_true')),
            (['--wpsubdomain'],
                dict(help="create WordPress multisite with subdomain setup",
                     action='store_true')),
            (['--wpfc'],
                dict(help="create WordPress single/multi site with "
                     "Nginx fastcgi_cache",
                     action='store_true')),
            (['--wpsc'],
                dict(help="create WordPress single/multi site with wpsc cache",
                     action='store_true')),
            (['--wprocket'],
             dict(help="create WordPress single/multi site with WP-Rocket",
                  action='store_true')),
            (['--wpce'],
             dict(help="create WordPress single/multi site with Cache-Enabler",
                  action='store_true')),
            (['--wpredis'],
                dict(help="create WordPress single/multi site "
                     "with redis cache",
                     action='store_true')),
            (['--alias'],
                dict(help="domain name to redirect to",
                     action='store', nargs='?')),
            (['--subsiteof'],
                dict(help="create a subsite of a multisite install",
                     action='store', nargs='?')),
            (['-le', '--letsencrypt'],
                dict(help="configure letsencrypt ssl for the site",
                     action='store' or 'store_const',
                     choices=('on', 'subdomain', 'wildcard'),
                     const='on', nargs='?')),
            (['--force'],
                dict(help="force Let's Encrypt certificate issuance",
                     action='store_true')),
            (['--dns'],
                dict(help="choose dns provider api for letsencrypt",
                     action='store' or 'store_const',
                     const='dns_cf', nargs='?')),
            (['--dnsalias'],
                dict(help="set domain used for acme dns alias validation",
                     action='store', nargs='?')),
            (['--hsts'],
                dict(help="enable HSTS for site secured with letsencrypt",
                     action='store_true')),
            (['--ngxblocker'],
                dict(help="enable HSTS for site secured with letsencrypt",
                     action='store_true')),
            (['--user'],
                dict(help="provide user for WordPress site")),
            (['--email'],
                dict(help="provide email address for WordPress site")),
            (['--pass'],
                dict(help="provide password for WordPress user",
                     dest='wppass')),
            (['--proxy'],
                dict(help="create proxy for site", nargs='+')),
            (['--vhostonly'], dict(help="only create vhost and database "
                                   "without installing WordPress",
                                   action='store_true')),
            (['--secure'],
                dict(help="enable HTTP basic authentication", action='store_true')),
        ]
        for php_version, php_number in WOVar.wo_php_versions.items():
            arguments.append(([f'--{php_version}'],
                              dict(help=f'Create PHP {php_number} site',
                                   action='store_true')))

    def _get_site_name_input(self, pargs):
        """Get site name from user input if not provided"""
        if not pargs.site_name:
            try:
                while not pargs.site_name:
                    pargs.site_name = (input('Enter site name : ').strip())
            except IOError as e:
                Log.debug(self, str(e))
                Log.error(self, "Unable to input site name, Please try again!")

    def _validate_domain_and_setup(self, pargs):
        """Validate domain and setup basic domain variables"""
        pargs.site_name = pargs.site_name.strip()
        wo_domain = WODomain.validate(self, pargs.site_name)
        wo_www_domain = f"www.{wo_domain}"
        (wo_domain_type, wo_root_domain) = WODomain.getlevel(self, wo_domain)

        if not wo_domain.strip():
            Log.error(self, "Invalid domain name, Provide valid domain name")

        wo_site_webroot = WOVar.wo_webroot + wo_domain

        # Check if domain already exists
        if check_domain_exists(self, wo_domain):
            Log.error(self, f"site {wo_domain} already exists")
        elif os.path.isfile(f'/etc/nginx/sites-available/{wo_domain}'):
            Log.error(self, f"Nginx configuration /etc/nginx/sites-available/"
                      f"{wo_domain} already exists")

        return wo_domain, wo_www_domain, wo_domain_type, wo_root_domain, wo_site_webroot

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs

        # Determine site type and get additional configuration
        try:
            stype, cache, extra_info = determine_site_type(pargs)
        except SiteError as e:
            Log.debug(self, str(e))
            Log.error(self, str(e))

        # Extract additional info for different site types
        host = extra_info.get('host')
        port = extra_info.get('port')
        alias_name = extra_info.get('alias_name')
        subsiteof_name = extra_info.get('subsiteof_name')

        # Get site name from user if needed
        self._get_site_name_input(pargs)

        # Validate domain and setup variables
        wo_domain, wo_www_domain, wo_domain_type, wo_root_domain, wo_site_webroot = \
            self._validate_domain_and_setup(pargs)

        if stype == 'proxy':
            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=True, basic=True, wp=False,
                wpfc=False, wpsc=False, wprocket=False, wpce=False,
                multisite=False, wpsubdir=False, webroot=wo_site_webroot,
                proxy=True, host=host, port=port)

        if stype == 'alias':
            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=True, basic=True, wp=False,
                wpfc=False, wpsc=False, wprocket=False, wpce=False,
                multisite=False, wpsubdir=False, webroot=wo_site_webroot,
                alias=True, alias_name=alias_name)

        if stype == 'subsite':
            # Get parent site data
            parent_site_info = getSiteInfo(self, subsiteof_name)
            if not parent_site_info:
                Log.error(self, "Parent site {0} does not exist"
                          .format(subsiteof_name))
            if not parent_site_info.is_enabled:
                Log.error(self, "Parent site {0} is not enabled"
                          .format(subsiteof_name))
            if parent_site_info.site_type not in ['wpsubdomain', 'wpsubdir']:
                Log.error(self, "Parent site {0} is not WordPress multisite"
                          .format(subsiteof_name))

            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=False, basic=False, multisite=False, webroot=wo_site_webroot)

            data["wp"] = parent_site_info.site_type == 'wp'
            data["wpfc"] = parent_site_info.cache_type == 'wpfc'
            data["wpsc"] = parent_site_info.cache_type == 'wpsc'
            data["wprocket"] = parent_site_info.cache_type == 'wprocket'
            data["wpce"] = parent_site_info.cache_type == 'wpce'
            data["wpredis"] = parent_site_info.cache_type == 'wpredis'
            data["wpsubdir"] = parent_site_info.site_type == 'wpsubdir'
            data["wo_php"] = ("php" + parent_site_info.php_version).replace(".", "")
            data['subsite'] = True
            data['subsiteof_name'] = subsiteof_name
            data['subsiteof_webroot'] = parent_site_info.site_path

        # Use centralized PHP version management instead of hardcoded checks
        if PHPVersionManager.has_any_php_version(pargs):
            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=False, basic=False,
                wp=False, wpfc=False, wpsc=False, wprocket=False,
                wpce=False, multisite=False,
                wpsubdir=False, webroot=wo_site_webroot)
            data['basic'] = True

        if stype in ['html', 'php']:
            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=True, basic=False, wp=False,
                wpfc=False, wpsc=False, wprocket=False, wpce=False,
                multisite=False, wpsubdir=False, webroot=wo_site_webroot)

            if stype == 'php':
                data['static'] = False
                data['basic'] = True

        elif stype in ['mysql', 'wp', 'wpsubdir', 'wpsubdomain']:

            data = dict(
                site_name=wo_domain, www_domain=wo_www_domain,
                static=False, basic=True, wp=False, wpfc=False,
                wpsc=False, wpredis=False, wprocket=False, wpce=False,
                multisite=False, wpsubdir=False, webroot=wo_site_webroot,
                wo_db_name='', wo_db_user='', wo_db_pass='',
                wo_db_host='')

            if stype in ['wp', 'wpsubdir', 'wpsubdomain']:
                data['wp'] = True
                data['basic'] = False
                data[cache] = True
                data['wp-user'] = pargs.user
                data['wp-email'] = pargs.email
                data['wp-pass'] = pargs.wppass
                if stype in ['wpsubdir', 'wpsubdomain']:
                    data['multisite'] = True
                    if stype == 'wpsubdir':
                        data['wpsubdir'] = True
        else:
            pass

        # Initialize all PHP versions to False
        for version in WOVar.wo_php_versions:
            data[version] = False

        # Check for PHP versions in pargs
        for pargs_version, version in WOVar.wo_php_versions.items():
            if data and getattr(pargs, pargs_version, False):
                data[pargs_version] = True
                data['wo_php'] = pargs_version
                php_version = version
                break
        else:
            if self.app.config.has_section('php'):
                config_php_ver = self.app.config.get('php', 'version')

                for wo_key, php_ver in WOVar.wo_php_versions.items():
                    if php_ver == config_php_ver:
                        data[wo_key] = True
                        data['wo_php'] = wo_key
                        php_version = php_ver
                        break

        if ((not pargs.wpfc) and (not pargs.wpsc) and
            (not pargs.wprocket) and
            (not pargs.wpce) and
            (not pargs.wpredis) and
                (not pargs.subsiteof)):
            data['basic'] = True

        if (cache == 'wpredis'):
            cache = 'wpredis'
            data['wpredis'] = True
            data['basic'] = False
            pargs.wpredis = True

        # Define php-fpm variables for templates
        data['pool_name'] = wo_domain.replace('.', '-').lower()
        if 'wo_php' in data:
            data['php_ver'] = data['wo_php'].replace('php', '')
            data['php_fpm_user'] = f"php-{data['pool_name']}"

        # Check rerequired packages are installed or not
        wo_auth = site_package_check(self, stype)

        try:
            pre_run_checks(self)
        except SiteError as e:
            Log.debug(self, str(e))
            Log.error(self, "NGINX configuration check failed.")

        try:
            try:
                # setup NGINX configuration, and webroot
                setupdomain(self, data)

                # Fix Nginx Hashbucket size error
                hashbucket(self)
                self._render_protected(data, pargs.secure)
            except SiteError as e:
                # call cleanup actions on failure
                Log.debug(self, str(e))
                handle_site_error_cleanup(self, wo_domain, data['webroot'])

            if 'proxy' in data.keys() and data['proxy']:
                addNewSite(self, wo_domain, stype, cache, wo_site_webroot)
                # Service Nginx Reload
                if not WOService.reload_service(self, 'nginx'):
                    Log.info(self, Log.FAIL +
                             "There was a serious error encountered...")
                    Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                    doCleanupAction(self, domain=wo_domain)
                    deleteSiteInfo(self, wo_domain)
                    Log.error(self, "service nginx reload failed. "
                              "check issues with `nginx -t` command")
                    Log.error(self, "Check the log for details: "
                              "`tail /var/log/wo/wordops.log` "
                              "and please try again")
                if wo_auth and len(wo_auth):
                    for msg in wo_auth:
                        Log.info(self, Log.ENDC + msg, log=False)
                Log.info(self, "Successfully created site"
                         " http://{0}".format(wo_domain))

            elif 'alias' in data.keys() and data['alias']:
                addNewSite(self, wo_domain, stype, cache, wo_site_webroot)
                # Service Nginx Reload
                if not WOService.reload_service(self, 'nginx'):
                    Log.info(self, Log.FAIL +
                             "There was a serious error encountered...")
                    Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                    doCleanupAction(self, domain=wo_domain)
                    deleteSiteInfo(self, wo_domain)
                    Log.error(self, "service nginx reload failed. "
                              "check issues with `nginx -t` command")
                    Log.error(self, "Check the log for details: "
                              "`tail /var/log/wo/wordops.log` "
                              "and please try again")
                if wo_auth and len(wo_auth):
                    for msg in wo_auth:
                        Log.info(self, Log.ENDC + msg, log=False)
                Log.info(self, "Successfully created site"
                         " http://{0}".format(wo_domain))

            elif 'subsite' in data.keys() and data['subsite']:
                addNewSite(self, wo_domain, stype, cache, wo_site_webroot)
                # Service Nginx Reload
                if not WOService.reload_service(self, 'nginx'):
                    Log.info(self, Log.FAIL +
                             "There was a serious error encountered...")
                    Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                    doCleanupAction(self, domain=wo_domain)
                    deleteSiteInfo(self, wo_domain)
                    Log.error(self, "service nginx reload failed. "
                              "check issues with `nginx -t` command")
                    Log.error(self, "Check the log for details: "
                              "`tail /var/log/wo/wordops.log` "
                              "and please try again")
                if wo_auth and len(wo_auth):
                    for msg in wo_auth:
                        Log.info(self, Log.ENDC + msg, log=False)
                Log.info(self, "Successfully created site"
                         " http://{0}".format(wo_domain))

            else:
                if not php_version:
                    php_version = None
                addNewSite(self, wo_domain, stype, cache, wo_site_webroot,
                           php_version=php_version)

            # Setup database for MySQL site
            if 'wo_db_name' in data.keys() and not data['wp']:
                try:
                    data = setupdatabase(self, data)
                    # Add database information for site into database
                    updateSiteInfo(self, wo_domain, db_name=data['wo_db_name'],
                                   db_user=data['wo_db_user'],
                                   db_password=data['wo_db_pass'],
                                   db_host=data['wo_db_host'])
                except SiteError as e:
                    # call cleanup actions on failure
                    Log.debug(self, str(e))
                    handle_site_error_cleanup(self, wo_domain, data['webroot'],
                                            data['wo_db_name'], data['wo_db_user'],
                                            data['wo_db_host'])

                try:
                    wodbconfig = open("{0}/wo-config.php"
                                      .format(wo_site_webroot),
                                      encoding='utf-8', mode='w')
                    wodbconfig.write("<?php \ndefine('DB_NAME', '{0}');"
                                     "\ndefine('DB_USER', '{1}'); "
                                     "\ndefine('DB_PASSWORD', '{2}');"
                                     "\ndefine('DB_HOST', '{3}');\n?>"
                                     .format(data['wo_db_name'],
                                             data['wo_db_user'],
                                             data['wo_db_pass'],
                                             data['wo_db_host']))
                    wodbconfig.close()
                    stype = 'mysql'
                except IOError as e:
                    Log.debug(self, str(e))
                    Log.debug(self, "Error occured while generating wo-config.php")
                    handle_site_error_cleanup(self, wo_domain, data['webroot'],
                                            data['wo_db_name'], data['wo_db_user'],
                                            data['wo_db_host'])

            # Setup WordPress if Wordpress site
            if data['wp']:
                vhostonly = bool(pargs.vhostonly)
                try:
                    wo_wp_creds = setupwordpress(self, data, vhostonly)
                    # Add database information for site into database
                    updateSiteInfo(self, wo_domain,
                                   db_name=data['wo_db_name'],
                                   db_user=data['wo_db_user'],
                                   db_password=data['wo_db_pass'],
                                   db_host=data['wo_db_host'])
                except SiteError as e:
                    # call cleanup actions on failure
                    Log.debug(self, str(e))
                    Log.info(self, Log.FAIL +
                             "There was a serious error encountered...")
                    Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                    doCleanupAction(self, domain=wo_domain,
                                    webroot=data['webroot'],
                                    dbname=data['wo_db_name'],
                                    dbuser=data['wo_db_user'],
                                    dbhost=data['wo_mysql_grant_host'])
                    deleteSiteInfo(self, wo_domain)
                    Log.error(self, "Check the log for details: "
                              "`tail /var/log/wo/wordops.log` "
                              "and please try again")

            # Service Nginx Reload call cleanup if failed to reload nginx
            # Configure php-fpm pool for the site
            try:
                setup_php_fpm(self, data)
            except SiteError as e:
                Log.debug(self, str(e))
                Log.info(self, Log.FAIL +
                         "There was a serious error encountered...")
                Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                doCleanupAction(self, domain=wo_domain,
                                webroot=data['webroot'])
                if 'wo_db_name' in data.keys():
                    doCleanupAction(self, domain=wo_domain,
                                    dbname=data['wo_db_name'],
                                    dbuser=data['wo_db_user'],
                                    dbhost=data['wo_mysql_grant_host'])
                deleteSiteInfo(self, wo_domain)
                Log.error(self, "Check the log for details: "
                          "`tail /var/log/wo/wordops.log` "
                          "and please try again")

            if not WOService.reload_service(self, 'nginx'):
                Log.info(self, Log.FAIL +
                         "There was a serious error encountered...")
                Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                doCleanupAction(self, domain=wo_domain,
                                webroot=data['webroot'])
                if 'wo_db_name' in data.keys():
                    doCleanupAction(self, domain=wo_domain,
                                    dbname=data['wo_db_name'],
                                    dbuser=data['wo_db_user'],
                                    dbhost=data['wo_mysql_grant_host'])
                deleteSiteInfo(self, wo_domain)
                Log.info(self, Log.FAIL + "service nginx reload failed."
                         " check issues with `nginx -t` command.")
                Log.error(self, "Check the log for details: "
                          "`tail /var/log/wo/wordops.log` "
                          "and please try again")

            WOGit.add(self, ["/etc/nginx"],
                      msg="{0} created with {1} {2}"
                      .format(wo_www_domain, stype, cache))
            # Setup Permissions for webroot
            try:
                setwebrootpermissions(self, data['webroot'],
                                      data.get('php_fpm_user',
                                               WOVar.wo_php_user))
            except SiteError as e:
                Log.debug(self, str(e))
                Log.info(self, Log.FAIL +
                         "There was a serious error encountered...")
                Log.info(self, Log.FAIL + "Cleaning up afterwards...")
                doCleanupAction(self, domain=wo_domain,
                                webroot=data['webroot'])
                if 'wo_db_name' in data.keys():
                    print("Inside db cleanup")
                    doCleanupAction(self, domain=wo_domain,
                                    dbname=data['wo_db_name'],
                                    dbuser=data['wo_db_user'],
                                    dbhost=data['wo_mysql_grant_host'])
                deleteSiteInfo(self, wo_domain)
                Log.error(self, "Check the log for details: "
                          "`tail /var/log/wo/wordops.log` and "
                          "please try again")

            if wo_auth and len(wo_auth):
                for msg in wo_auth:
                    Log.info(self, Log.ENDC + msg, log=False)

            if data['wp'] and (not pargs.vhostonly):
                Log.info(self, Log.ENDC + "WordPress admin user :"
                         " {0}".format(wo_wp_creds['wp_user']), log=False)
                Log.info(self, Log.ENDC + "WordPress admin password : {0}"
                         .format(wo_wp_creds['wp_pass']), log=False)

                display_cache_settings(self, data)

            Log.info(self, "Successfully created site"
                     " http://{0}".format(wo_domain))
        except SiteError:
            Log.error(self, "Check the log for details: "
                      "`tail /var/log/wo/wordops.log` and please try again")

        # Setup Let's Encrypt SSL if requested
        if pargs.letsencrypt:
            data['letsencrypt'] = True
            setup_letsencrypt_advanced(self, wo_domain, pargs,
                                     wo_domain_type, wo_root_domain,
                                     wo_site_webroot)

    def _render_protected(self, data, secure):
        slug = data.get('pool_name')
        if not slug:
            return
        acl_dir = f'/etc/nginx/acl/{slug}'
        os.makedirs(acl_dir, exist_ok=True)
        protected = os.path.join(acl_dir, 'protected.conf')
        pdata = {
            'slug': slug,
            'wp': data.get('wp', False),
            'php_ver': data.get('php_ver'),
            'pool_name': data.get('pool_name'),
            'secure': secure,
        }
        WOTemplate.deploy(self, protected, 'protected.mustache', pdata, overwrite=True)
        if secure:
            passwd = RANDOM.long(self)
            username = data.get('wo_user', WOVar.wo_user)
            cred = os.path.join(acl_dir, 'credentials')
            WOShellExec.cmd_exec(
                self,
                f"printf \"{username}:$(openssl passwd -apr1 {passwd} 2>/dev/null)\\n\" > {cred} 2>/dev/null",
                log=False)
            Log.info(self, f"HTTP Auth User : {username}")
            Log.info(self, f"HTTP Auth Password : {passwd}")
