import os
from getpass import getpass

from cement.core.controller import CementBaseController, expose
from wo.cli.plugins.site_functions import (
    check_domain_exists, pre_run_checks, setupdomain,
    setupdatabase, setwebrootpermissions, setup_php_fpm, setup_letsencrypt,
    parse_wp_db_config, copy_nginx_acl_files,
    build_clone_site_data, clone_database, clone_website_files, update_wordpress_urls,
    generate_wp_config_for_clone)
from wo.cli.plugins.sitedb import addNewSite, updateSiteInfo, getSiteInfo
from wo.core.domainvalidate import WODomain
from wo.core.logging import Log
from wo.core.nginxhashbucket import hashbucket
from wo.core.services import WOService
from wo.core.variables import WOVar
from wo.core.fileutils import WOFileUtils

class WOSiteCloneController(CementBaseController):
    class Meta:
        label = 'clone'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = 'clone an existing WordPress site (WordPress sites only)'
        arguments = [
            (['site_name'], dict(help='source WordPress site to clone', nargs='?')),
            (['newsite_name'], dict(help='destination site name', nargs='?')),
            (['--user'], dict(help='WordPress admin user for the cloned site')),
            (['--email'], dict(help='WordPress admin email for the cloned site')),
            (['--pass'], dict(help='WordPress admin password for the cloned site', dest='wppass')),
        ]

    def _get_site_names(self, pargs):
        """Get and validate source and destination site names."""
        src = pargs.site_name or input('Enter source site name : ').strip()
        dest = pargs.newsite_name or input('Enter destination site name : ').strip()

        # Validate domains
        src = WODomain.validate(self, src)
        dest = WODomain.validate(self, dest)

        return src, dest

    def _validate_sites(self, src, dest):
        """Validate that source exists and destination doesn't exist."""
        if not check_domain_exists(self, src):
            Log.error(self, f"source site {src} does not exist")
        if check_domain_exists(self, dest):
            Log.error(self, f"destination site {dest} already exists")

    def _get_wp_credentials(self, pargs, src):
        """Get WordPress admin credentials."""
        wpuser = pargs.user or WOVar.wo_user
        wpemail = pargs.email or WOVar.wo_email
        wppass = pargs.wppass or getpass(f"Enter admin password for {wpuser}: ")

        if not wppass:
            Log.error(self, 'password cannot be empty')

        return {
            'wp-user': wpuser,
            'wp-email': wpemail,
            'wp-pass': wppass
        }

    def _setup_destination_site(self, src_info, data, dest):
        """Setup the destination site infrastructure."""
        # Setup domain and database infrastructure
        pre_run_checks(self)
        setupdomain(self, data)
        hashbucket(self)

        # Add site to database
        addNewSite(self, dest, src_info.site_type,
                   src_info.cache_type if src_info.cache_type else 'basic',
                   data['webroot'], php_version=src_info.php_version)

        # Setup database
        data = setupdatabase(self, data)

        # Update site information
        updateSiteInfo(self, dest, db_name=data['wo_db_name'],
                       db_user=data['wo_db_user'], db_password=data['wo_db_pass'],
                       db_host=data['wo_db_host'], php_version=src_info.php_version,
                       stype=src_info.site_type,
                       cache=src_info.cache_type if src_info.cache_type else 'basic')

        # Setup PHP-FPM
        setup_php_fpm(self, data)

        return data

    @expose(hide=True)
    def default(self):
        """
        Main entry point for site cloning - refactored for orchestration-only logic.
        """
        pargs = self.app.pargs

        # 1. Get and validate site names
        src, dest = self._get_site_names(pargs)
        self._validate_sites(src, dest)

        # 2. Get source site information
        src_info = getSiteInfo(self, src)
        if not src_info:
            Log.error(self, f"source site {src} does not exist")

        # 2a. Validate that source is a WordPress site
        if not src_info.site_type or 'wp' not in src_info.site_type:
            Log.error(self, f"Site cloning is only supported for WordPress sites.\n"
                           f"Source site '{src}' is of type: '{src_info.site_type or 'unknown'}'\n"
                           f"WordPress site types include: wp, wpsubdir, wpsubdomain\n"
                           f"For non-WordPress sites, consider manual file copying or backup/restore operations.")

        Log.info(self, f"Cloning WordPress site '{src}' (type: {src_info.site_type}) to '{dest}'")

        # 3. Get WordPress credentials
        wp_credentials = self._get_wp_credentials(pargs, src)

        # 4. Build site configuration data
        (dest_type, _) = WODomain.getlevel(self, dest)
        data = build_clone_site_data(src_info, src, dest, wp_credentials, dest_type)

        # 5. Setup destination site infrastructure
        data = self._setup_destination_site(src_info, data, dest)

        # 6. Copy nginx ACL files
        src_slug = src.replace('.', '-').lower()
        dest_slug = dest.replace('.', '-').lower()
        copy_nginx_acl_files(self, src_slug, dest_slug)

        # 7. Parse source database configuration
        conf_src = os.path.join(WOVar.wo_webroot, src, 'wp-config.php')
        src_db_config = parse_wp_db_config(conf_src)
        dest_db_config = {
            'DB_NAME': data['wo_db_name'],
            'DB_USER': data['wo_db_user'],
            'DB_PASSWORD': data['wo_db_pass'],
            'DB_HOST': data['wo_db_host'],
        }

        # 8. Clone database
        clone_database(self, src, src_db_config, dest_db_config)

        # 9. Clone website files from source to destination
        clone_website_files(self, src, dest)

        # 10. Generate ONLY wp-config.php for cloned site (preserves all cloned files)
        generate_wp_config_for_clone(self, data)

        # 11. Update WordPress URLs in database
        update_wordpress_urls(self, src, dest, data['webroot'])

        # 12. Set proper permissions
        conf_dest = os.path.join(WOVar.wo_webroot, dest, 'wp-config.php')
        dest_htdocs = os.path.join(data['webroot'], 'htdocs')
        setwebrootpermissions(self, dest_htdocs, data['php_fpm_user'])
        WOFileUtils.chown(self, conf_dest, data['php_fpm_user'], data['php_fpm_user'])

        # 13. Reload nginx
        WOService.reload_service(self, 'nginx')

        # 14. Setup SSL if source has SSL
        if src_info.is_ssl:
            setup_letsencrypt(self, dest, data['webroot'])

        # 15. Success message
        Log.info(self, f"Successfully cloned '{src}' → '{dest}'")
