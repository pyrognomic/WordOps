import getpass
import glob
import json
import os
import random
import re
import shlex
import shutil
import string
import subprocess
from subprocess import CalledProcessError

from wo.cli.plugins.sitedb import getSiteInfo, updateSiteInfo, deleteSiteInfo
from wo.cli.plugins.stack import WOStackController
from wo.cli.plugins.stack_pref import post_pref
from wo.core.acme import WOAcme
from wo.core.aptget import WOAptGet
from wo.core.domainvalidate import WODomain
from wo.core.fileutils import WOFileUtils
from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.mysql import (MySQLConnectionError, StatementExcecutionError,
                           WOMysql)
from wo.core.services import WOService
from wo.core.shellexec import CommandExecutionError, WOShellExec
from wo.core.sslutils import SSL
from wo.core.variables import WOVar

# Site Functions Constants
SITE_CONSTANTS = {
    'DEFAULT_PASSWORD_LENGTH': 24,
    'DEFAULT_DB_NAME_LENGTH': 32,
    'DEFAULT_USERNAME_LENGTH': 12,
    'DEFAULT_WP_PREFIX': 'wp_',
    'DEFAULT_WP_USER': 'admin',
    'DEVNULL_PATH': os.devnull,
    'NGINX_CONFIG_PATH': '/etc/nginx/sites-available',
    'NGINX_ENABLED_PATH': '/etc/nginx/sites-enabled',
    'NGINX_LOG_PATH': '/var/log/nginx',
    'WEBROOT_BASE': '/var/www',
    'WP_CLI_TIMEOUT': 300,
    'MYSQL_DUMP_OPTIONS': '--single-transaction --hex-blob'
}

BACKUP_SITE_TYPES = ['html', 'php', 'proxy', 'mysql']

# Shared utility functions
def execute_command_safely(controller, command, error_message, log_command=True):
    """Execute shell command with standardized error handling"""
    try:
        ok = WOShellExec.cmd_exec(controller, command, log=log_command)
        if not ok:
            raise SiteError(error_message)
        return True
    except CommandExecutionError as e:
        Log.debug(controller, str(e))
        raise SiteError(error_message)

def log_success(controller, message="Done"):
    """Standardized success logging"""
    Log.info(controller, f"[{Log.ENDC}{message}{Log.OKBLUE}]")

def log_failure(controller, message="Failed"):
    """Standardized failure logging"""
    Log.info(controller, f"[{Log.ENDC}{Log.FAIL}{message}{Log.OKBLUE}]")

def build_wp_command(action, *args, **kwargs):
    base_cmd = f"{WOVar.wo_wpcli_path} --allow-root {action}"

    arg_tokens = []
    for arg in args:
        if arg is None:
            continue
        arg_text = str(arg)
        if not arg_text:
            continue
        arg_tokens.append(shlex.quote(arg_text))

    if arg_tokens:
        base_cmd += " " + " ".join(arg_tokens)

    if kwargs:
        options = []
        for key, value in kwargs.items():
            if isinstance(value, bool):
                if value:
                    options.append(f"--{key}")
            elif value is None:
                options.append(f"--{key}")
            else:
                options.append(f"--{key}={shlex.quote(str(value))}")
        if options:
            base_cmd += " " + " ".join(options)

    return base_cmd

def validate_input_regex(value, pattern, error_message):
    """Validate input against regex pattern"""
    if not re.match(pattern, value):
        raise SiteError(error_message)
    return True


class SiteError(Exception):
    """Custom Exception Occured when setting up site"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return repr(self.message)


class PHPVersionManager:
    """Centralized PHP version management to eliminate scattered version checks"""

    SUPPORTED_VERSIONS = ['php74', 'php80', 'php81', 'php82', 'php83', 'php84']

    # Version mapping for different contexts
    VERSION_MAP = {
        'php74': '7.4',
        'php80': '8.0',
        'php81': '8.1',
        'php82': '8.2',
        'php83': '8.3',
        'php84': '8.4'
    }

    @classmethod
    def get_selected_versions(cls, pargs):
        """Get all selected PHP versions from parsed arguments"""
        return [version for version in cls.SUPPORTED_VERSIONS
                if hasattr(pargs, version) and getattr(pargs, version)]

    @classmethod
    def validate_single_version(cls, pargs):
        """Ensure only one PHP version is selected and return it"""
        selected = cls.get_selected_versions(pargs)

        if len(selected) > 1:
            raise SiteError(f"Error: Cannot combine multiple PHP versions: {', '.join(selected)}. "
                          "Please select only one PHP version.")

        return selected[0] if selected else None

    @classmethod
    def is_php_version(cls, option):
        """Check if an option is a PHP version"""
        return option in cls.SUPPORTED_VERSIONS

    @classmethod
    def get_version_number(cls, php_option):
        """Convert PHP option (e.g., 'php84') to version number (e.g., '8.4')"""
        return cls.VERSION_MAP.get(php_option, None)

    @classmethod
    def has_any_php_version(cls, pargs):
        """Check if any PHP version is specified"""
        return len(cls.get_selected_versions(pargs)) > 0


def pre_run_checks(self):

    # Check nginx configuration
    Log.wait(self, "Running pre-run checks")
    try:
        Log.debug(self, "checking NGINX configuration ...")
        with open('/dev/null', 'w') as fnull:
            subprocess.check_call(["/usr/sbin/nginx", "-t"], stdout=fnull, stderr=subprocess.STDOUT)
    except CalledProcessError as e:
        Log.failed(self, "Running pre-update checks")
        Log.debug(self, f"{e}")
        raise SiteError("nginx configuration check failed.")
    else:
        Log.valide(self, "Running pre-update checks")

def _create_nginx_config(controller, domain_name, data):
    """Create and validate nginx configuration file"""
    Log.info(controller, "Setting up NGINX configuration \t", end='')

    config_path = f"{SITE_CONSTANTS['NGINX_CONFIG_PATH']}/{domain_name}"

    try:
        with open(config_path, 'w', encoding='utf-8') as nginx_conf:
            controller.app.render(data, 'virtualconf.mustache', out=nginx_conf)
    except (IOError, Exception) as e:
        Log.debug(controller, str(e))
        raise SiteError("create nginx configuration failed for site")

    # Validate nginx configuration
    try:
        Log.debug(controller, "Checking generated nginx conf, please wait...")
        with open(SITE_CONSTANTS['DEVNULL_PATH'], 'w') as fnull:
            subprocess.check_call(["/usr/sbin/nginx", "-t"],
                                stdout=fnull, stderr=subprocess.STDOUT)
        log_success(controller)
    except CalledProcessError as e:
        Log.debug(controller, str(e))
        log_failure(controller)
        raise SiteError("created nginx configuration failed for site. check with `nginx -t`")


def _create_nginx_symlink(controller, domain_name):
    """Create symbolic link to enable nginx site"""
    available_path = f"{SITE_CONSTANTS['NGINX_CONFIG_PATH']}/{domain_name}"
    enabled_path = f"{SITE_CONSTANTS['NGINX_ENABLED_PATH']}/{domain_name}"
    WOFileUtils.create_symlink(controller, [available_path, enabled_path])


def _setup_webroot_directories(controller, domain_name, webroot):
    """Create webroot directories and log symlinks"""
    Log.info(controller, "Setting up webroot \t\t", end='')

    directories = [
        f'{webroot}/htdocs',
        f'{webroot}/logs',
        f'{webroot}/conf/nginx'
    ]

    try:
        # Create directories
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)

        # Create log symlinks
        log_types = ['access', 'error']
        for log_type in log_types:
            nginx_log = f"{SITE_CONSTANTS['NGINX_LOG_PATH']}/{domain_name}.{log_type}.log"
            site_log = f"{webroot}/logs/{log_type}.log"
            WOFileUtils.create_symlink(controller, [nginx_log, site_log])

    except Exception as e:
        Log.debug(controller, str(e))
        raise SiteError("setup webroot failed for site")

    # Verify directories were created
    required_dirs = [f'{webroot}/htdocs', f'{webroot}/logs']
    if all(os.path.exists(directory) for directory in required_dirs):
        log_success(controller)
    else:
        log_failure(controller)
        raise SiteError("setup webroot failed for site")


def check_domain_exists(self, domain):
    if getSiteInfo(self, domain):
        return True
    return False


def setupdomain(self, data):
    """
    Setup domain configuration - refactored for better maintainability.

    Args:
        data (dict): Site configuration data containing 'site_name' and 'webroot'
    """
    domain_name = data['site_name']
    webroot = data['webroot']

    # Create and validate nginx configuration
    _create_nginx_config(self, domain_name, data)

    # Enable the site by creating symlink
    _create_nginx_symlink(self, domain_name)

    # Setup webroot directories and log symlinks
    _setup_webroot_directories(self, domain_name, webroot)


def setup_php_fpm(self, data):
    if 'php_ver' not in data:
        Log.debug(self, 'No php version specified, skipping php-fpm setup')
        return

    slug = data.get('pool_name')
    php_ver = data.get('php_ver')
    wo_php_key = data.get('wo_php')
    php_version = WOVar.wo_php_versions.get(wo_php_key)
    php_fpm_user = data.get('php_fpm_user', f'php-{slug}')
    webroot = data.get('webroot')

    if not (slug and php_ver and php_version and webroot):
        raise SiteError('Incomplete PHP-FPM configuration data')

    Log.info(self, 'Configuring PHP-FPM pool \t', end='')
    try:
        # create system user and group
        WOShellExec.cmd_exec(self,
                             f"getent group {php_fpm_user} > /dev/null 2>&1 || groupadd -r {php_fpm_user}")
        WOShellExec.cmd_exec(self,
                             f"id -u {php_fpm_user} > /dev/null 2>&1 || useradd -r -g {php_fpm_user} -M -d /nonexistent -s /usr/sbin/nologin {php_fpm_user}")
        # add nginx user to php-fpm-user group (grant perm to connect to php-fpm socket)
        WOShellExec.cmd_exec(self,
                             f"usermod -aG {php_fpm_user} {WOVar.wo_php_user}")

        log_dir = f"/var/log/php/{php_version}/{slug}"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        WOFileUtils.chown(self, log_dir, php_fpm_user, php_fpm_user, recursive=True)

        service_path = f"/etc/systemd/system/php{php_version}-fpm@.service"
        service_data = {'php_ver': php_ver, 'php_version': php_version}
        if not os.path.isfile(service_path):
            with open(service_path, 'w') as service_file:
                self.app.render(service_data, 'php-fpm-service.mustache',
                                out=service_file)

        master_path = f"/etc/php/{php_version}/fpm/php-fpm-{slug}.conf"
        with open(master_path, 'w') as master_file:
            self.app.render({'php_version': php_version,
                             'slug': slug}, 'php-fpm-master.mustache',
                            out=master_file)

        pool_path = f"/etc/php/{php_version}/fpm/pool.d/{slug}.conf"
        pool_data = {'php_ver': php_ver, 'php_version': php_version,
                     'slug': slug, 'php_fpm_user': php_fpm_user,
                     'webroot': webroot}
        with open(pool_path, 'w') as pool_file:
            self.app.render(pool_data, 'php-fpm-pool.mustache',
                            out=pool_file)

        WOShellExec.cmd_exec(self, 'systemctl daemon-reload')
        WOShellExec.cmd_exec(self, f'systemctl enable php{php_version}-fpm@{slug}')
        WOService.restart_service(self, f'php{php_version}-fpm@{slug}')
    except Exception as e:
        Log.debug(self, str(e))
        raise SiteError('php-fpm setup failed')
    else:
        Log.info(self, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")

def cleanup_php_fpm(self, slug, php_ver, php_version, delete_vhost=True):
    """Remove old php-fpm configuration for a site"""
    Log.info(self, 'Removing old PHP-FPM config\t', end='')
    try:
        # Templated unit name; systemd accepts with or without .service
        service = f'php{php_version}-fpm@{slug}.service'

        # Best-effort stop/disable (do not fail cleanup if missing/not enabled)
        try:
            WOService.stop_service(self, service)
        except Exception as e:
            Log.debug(self, f"Stop service ignored: {e}")

        # Disable may fail if unit doesn't exist or isn't enabled → don't abort
        WOShellExec.cmd_exec(self, f'systemctl disable {service} || true', log=False)

        php_fpm_user = f'php-{slug}'
        if delete_vhost:
            # Ignore if already absent
            WOShellExec.cmd_exec(self, f'userdel {php_fpm_user} || true', log=False)
            WOShellExec.cmd_exec(self, f'groupdel {php_fpm_user} || true', log=False)

        # Paths to clean. Keep php_ver/php_version consistent with how they’re created.
        paths = [
            f'/etc/php/{php_version}/fpm/php-fpm-{slug}.conf',
            f'/etc/php/{php_version}/fpm/pool.d/{slug}.conf',
            f'/var/log/php/{php_version}/{slug}',
            f'/run/php/php{php_ver}-fpm-{slug}.sock',
            f'/run/php/php{php_version}-fpm-{slug}.pid',
        ]

        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
            except FileNotFoundError:
                pass
            except Exception as e:
                Log.debug(self, f"Failed to remove {path}: {e}")

        # Reload units even if disable failed
        WOShellExec.cmd_exec(self, 'systemctl daemon-reload', log=False)

    except Exception as e:
        Log.debug(self, str(e))
        raise SiteError('php-fpm cleanup failed')
    else:
        Log.info(self, '[' + Log.ENDC + 'Done' + Log.OKBLUE + ']')

def _process_domain_for_database(domain_name):
    """
    Process domain name for database naming conventions.

    Args:
        domain_name (str): The domain name to process

    Returns:
        dict: Processed domain variations
    """
    wo_replace_dash = domain_name.replace('-', '_')
    wo_replace_dot = wo_replace_dash.replace('.', '_')
    wo_replace_underscore = wo_replace_dot.replace('_', '')

    return {
        'dot_replaced': wo_replace_dot,
        'underscore_removed': wo_replace_underscore,
        'original': domain_name
    }


def _get_mysql_config(controller):
    """
    Get MySQL configuration settings with defaults.

    Args:
        controller: The controller object with app config

    Returns:
        dict: MySQL configuration
    """
    if controller.app.config.has_section('mysql'):
        return {
            'prompt_dbname': controller.app.config.get('mysql', 'db-name') in ['True', 'true'],
            'prompt_dbuser': controller.app.config.get('mysql', 'db-user') in ['True', 'true'],
            'grant_host': controller.app.config.get('mysql', 'grant-host')
        }
    else:
        return {
            'prompt_dbname': False,
            'prompt_dbuser': False,
            'grant_host': 'localhost'
        }


def _generate_database_name(domain_processed, max_length=32):
    """
    Generate a unique database name based on processed domain.

    Args:
        domain_processed (str): Processed domain name
        max_length (int): Maximum length for database name

    Returns:
        str: Generated database name
    """
    base_name = domain_processed[:max_length]
    random_suffix = generate_random(8)  # Use our unified random generator
    return f"{base_name}_{random_suffix}"


# WordPress plugin configurations - extracted from setupwordpress function
WP_NGINX_HELPER_CONFIG = {
    "fastcgi": {
        "log_level": "INFO",
        "log_filesize": 5,
        "enable_purge": 1,
        "enable_map": "0",
        "enable_log": 0,
        "enable_stamp": 1,
        "purge_homepage_on_new": 1,
        "purge_homepage_on_edit": 1,
        "purge_homepage_on_del": 1,
        "purge_archive_on_new": 1,
        "purge_archive_on_edit": 1,
        "purge_archive_on_del": 1,
        "purge_archive_on_new_comment": 0,
        "purge_archive_on_deleted_comment": 0,
        "purge_page_on_mod": 1,
        "purge_page_on_new_comment": 1,
        "purge_page_on_deleted_comment": 1,
        "cache_method": "enable_fastcgi",
        "purge_method": "get_request",
        "redis_hostname": "127.0.0.1",
        "redis_port": "6379",
        "redis_prefix": "nginx-cache:"
    },
    "redis": {
        "log_level": "INFO",
        "log_filesize": 5,
        "enable_purge": 1,
        "enable_map": "0",
        "enable_log": 0,
        "enable_stamp": 1,
        "purge_homepage_on_new": 1,
        "purge_homepage_on_edit": 1,
        "purge_homepage_on_del": 1,
        "purge_archive_on_new": 1,
        "purge_archive_on_edit": 1,
        "purge_archive_on_del": 1,
        "purge_archive_on_new_comment": 0,
        "purge_archive_on_deleted_comment": 0,
        "purge_page_on_mod": 1,
        "purge_page_on_new_comment": 1,
        "purge_page_on_deleted_comment": 1,
        "cache_method": "enable_redis",
        "purge_method": "get_request",
        "redis_hostname": "127.0.0.1",
        "redis_port": "6379",
        "redis_prefix": "nginx-cache:"
    }
}

WP_CACHE_ENABLER_CONFIG = {
    "cache_expires": 24,
    "clear_site_cache_on_saved_post": 1,
    "clear_site_cache_on_saved_comment": 0,
    "convert_image_urls_to_webp": 0,
    "clear_on_upgrade": 1,
    "compress_cache": 1,
    "excluded_post_ids": "",
    "excluded_query_strings": "",
    "excluded_cookies": "",
    "minify_inline_css_js": 1,
    "minify_html": 1
}

WP_CONFIG_VARIABLES = [
    ['WP_MEMORY_LIMIT', '256M'],
    ['WP_MAX_MEMORY_LIMIT', '512M'],
    ['CONCATENATE_SCRIPTS', 'false'],
    ['WP_POST_REVISIONS', '10'],
    ['MEDIA_TRASH', 'true'],
    ['EMPTY_TRASH_DAYS', '15'],
    ['WP_AUTO_UPDATE_CORE', 'minor'],
    ['WP_REDIS_DISABLE_BANNERS', 'true']
]


def _download_wordpress_core(controller, webroot):
    """Download WordPress core files"""
    WOFileUtils.chdir(controller, f'{webroot}/htdocs/')
    Log.info(controller, "Downloading WordPress \t\t", end='')
    try:
        if WOShellExec.cmd_exec(controller, f"{WOVar.wo_wpcli_path} --allow-root core download"):
            Log.info(controller, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")
        else:
            Log.info(controller, "[" + Log.ENDC + Log.FAIL + "Fail" + Log.OKBLUE + "]")
            raise SiteError("download WordPress core failed")
    except CommandExecutionError:
        Log.info(controller, "[" + Log.ENDC + Log.FAIL + "Fail" + Log.OKBLUE + "]")
        raise SiteError("download WordPress core failed")


def _setup_wp_prefix(controller, prompt_prefix):
    """Setup WordPress table prefix with validation"""
    wo_wp_prefix = 'wp_'  # Default value

    if prompt_prefix in ['True', 'true']:
        try:
            wo_wp_prefix = input('Enter the WordPress table prefix [wp_]: ')
            while wo_wp_prefix and not re.match('^[A-Za-z0-9_]*$', wo_wp_prefix):
                Log.warn(controller, "table prefix can only contain numbers, letters, and underscores")
                wo_wp_prefix = input('Enter the WordPress table prefix [wp_]: ')
        except EOFError:
            raise SiteError("input table prefix failed")

    return wo_wp_prefix or 'wp_'

def _create_wp_config_command(data, wp_prefix, skip_check: bool, extra_php: str):
    """
    Build wp-cli arguments (no shell) and return (args_list, extra_php_str).
    This function is intentionally 'dumb': it doesn't decide multisite logic.
    """
    args = [WOVar.wo_wpcli_path, "--allow-root", "config", "create"]
    if skip_check:
        args.append("--skip-check")

    # Pass DB settings as --opt=value; no shlex when using args list (no shell parsing).
    args += [
        f"--dbname={data['wo_db_name']}",
        f"--dbprefix={wp_prefix}",
        f"--dbuser={data['wo_db_user']}",
        f"--dbhost={data['wo_db_host']}",
        f"--dbpass={data['wo_db_pass']}",
        "--extra-php",
    ]

    # Ensure a trailing newline so wp-cli reads the whole snippet.
    if not extra_php.endswith("\n"):
        extra_php += "\n"

    return args, extra_php


def _create_wp_config(controller, data, wp_prefix, vhostonly):
    """
    Create wp-config.php using wp-cli.
    ALL multisite/single-site decisions live here (single source of truth).
    """
    Log.debug(controller, "Setting up wp-config file")

    is_multisite   = bool(data.get('multisite'))
    is_subdomain   = bool(data.get('wpsubdomain') or data.get('subdomain'))  # support either key if present
    skip_check     = bool(vhostonly)

    if is_multisite:
        Log.debug(controller, "Generating wp-config for WordPress multisite")
    else:
        Log.debug(controller, "Generating wp-config for WordPress single site")

    # Compose the PHP snippet once, based on mode.
    # Keep it minimal here; wp core multisite-install will add network constants later.
    extra_lines = ["define('WP_DEBUG', false);"]
    if is_multisite:
        # Useful with NGINX for MU file serving; harmless otherwise.
        extra_lines.append("define('WPMU_ACCEL_REDIRECT', true);")

    extra_php = "\n".join(extra_lines) + "\n"

    # Build args (no shell) and feed snippet via stdin.
    args, extra_php = _create_wp_config_command(data, wp_prefix, skip_check, extra_php)

    site_type = "multisite" if is_multisite else "single site"
    try:
        ok = WOShellExec.cmd_exec(controller, args, log=False, input_data=extra_php)
        if not ok:
            raise SiteError(f"generate wp-config failed for wp {site_type}")
    except CommandExecutionError:
        raise SiteError(f"generate wp-config failed for wp {site_type}")

def _configure_wp_variables(controller, domain_name):
    """Configure WordPress variables in wp-config.php"""
    # Add domain-specific Redis prefix
    wp_conf_variables = [['WP_REDIS_PREFIX', f'{domain_name}:']] + WP_CONFIG_VARIABLES

    Log.wait(controller, "Configuring WordPress")
    for wp_var, wp_val in wp_conf_variables:
        var_raw = wp_val in ['true', 'false']
        raw_flag = '--raw' if var_raw else ''

        try:
            cmd = f"/bin/bash -c \"{WOVar.wo_wpcli_path} --allow-root config set {wp_var} '{wp_val}' {raw_flag}\""
            WOShellExec.cmd_exec(controller, cmd)
        except CommandExecutionError as e:
            Log.failed(controller, "Configuring WordPress")
            Log.debug(controller, str(e))
            Log.error(controller, 'Unable to define wp-config.php variables')

    Log.valide(controller, "Configuring WordPress")


def _move_wp_config(controller, webroot):
    """Move wp-config.php outside webroot for security"""
    current_path = os.getcwd() + '/wp-config.php'
    target_path = os.path.abspath(os.path.join(os.getcwd(), os.pardir))

    try:
        Log.debug(controller, f"Moving file from {current_path} to {target_path}")
        shutil.move(current_path, target_path)
    except Exception as e:
        Log.debug(controller, str(e))
        Log.error(controller, f'Unable to move file from {current_path} to {target_path}', False)
        raise SiteError("Unable to move wp-config.php")


def _validate_wp_credentials(controller, wp_user, wp_email):
    """Validate WordPress user credentials with proper input handling"""
    # Validate username
    if not wp_user:
        wp_user = WOVar.wo_user

    username_regex = r'^[A-Za-z0-9 _\.\-@]+$'
    while not wp_user or not re.match(username_regex, wp_user):
        Log.warn(controller, "Username can have only alphanumeric characters, spaces, underscores, hyphens, periods and the @ symbol.")
        try:
            wp_user = input('Enter WordPress username: ')
        except EOFError:
            raise SiteError("input WordPress username failed")

    # Validate email
    if not wp_email:
        wp_email = WOVar.wo_email
        while not wp_email:
            try:
                wp_email = input('Enter WordPress email: ')
            except EOFError:
                raise SiteError("input WordPress username failed")

    # Email format validation
    email_regex = r"^[A-Za-z0-9\.\+_-]+@[A-Za-z0-9\._-]+\.[a-zA-Z]*$"
    try:
        while not re.match(email_regex, wp_email):
            Log.info(controller, "EMail not Valid in config, Please provide valid email id")
            wp_email = input("Enter your email: ")
    except EOFError:
        raise SiteError("input WordPress user email failed")

    return wp_user, wp_email


def _install_wordpress_core(controller, data, wp_user, wp_pass, wp_email):
    """Install WordPress core and setup database tables"""
    Log.debug(controller, "Setting up WordPress tables")
    Log.wait(controller, "Installing WordPress")

    base_cmd = f"{WOVar.wo_wpcli_path} --allow-root core"
    common_params = f"--url='{data['site_name']}' --title='{data['site_name']}' --admin_name='{wp_user}' --admin_password='{wp_pass}' --admin_email='{wp_email}'"

    if data['multisite']:
        Log.debug(controller, "Creating tables for WordPress multisite")
        subdomains_flag = '--subdomains' if not data.get('wpsubdir') else ''
        cmd = f"{base_cmd} multisite-install {common_params} {subdomains_flag}"
        error_msg = "setup WordPress tables failed for wp multi site"
    else:
        Log.debug(controller, "Creating tables for WordPress Single site")
        cmd = f"{base_cmd} install {common_params}"
        error_msg = "setup WordPress tables failed for single site"

    try:
        if not WOShellExec.cmd_exec(controller, cmd, log=False):
            Log.failed(controller, "Installing WordPress")
            raise SiteError(error_msg)
    except CommandExecutionError:
        raise SiteError(error_msg)

    Log.valide(controller, "Installing WordPress")


def _setup_wordpress_permalinks(controller):
    """Setup WordPress permalinks structure"""
    Log.debug(controller, "Updating WordPress permalink")
    try:
        cmd = f"{WOVar.wo_wpcli_path} --allow-root rewrite structure /%postname%/"
        WOShellExec.cmd_exec(controller, cmd)
    except CommandExecutionError as e:
        Log.debug(controller, str(e))
        raise SiteError("Update wordpress permalinks failed")


def _setup_cache_plugins(controller, data):
    """Setup cache plugins based on site configuration"""
    # Always install nginx-helper
    installwp_plugin(controller, 'nginx-helper', data)

    # Configure nginx-helper based on cache type
    if data.get('wpfc'):
        plugin_data = json.dumps(WP_NGINX_HELPER_CONFIG['fastcgi'])
        setupwp_plugin(controller, "nginx-helper", "rt_wp_nginx_helper_options", plugin_data, data)
    elif data.get('wpredis'):
        plugin_data = json.dumps(WP_NGINX_HELPER_CONFIG['redis'])
        setupwp_plugin(controller, 'nginx-helper', 'rt_wp_nginx_helper_options', plugin_data, data)

    # Install additional cache plugins
    if data.get('wpsc'):
        installwp_plugin(controller, 'wp-super-cache', data)

    if data.get('wpredis'):
        installwp_plugin(controller, 'redis-cache', data)

    if data.get('wpce'):
        installwp_plugin(controller, 'cache-enabler', data)
        plugin_data = json.dumps(WP_CACHE_ENABLER_CONFIG)
        setupwp_plugin(controller, 'cache-enabler', 'cache-enabler', plugin_data, data)

        # Enable WP_CACHE constant
        cmd = f"/bin/bash -c \"{WOVar.wo_wpcli_path} --allow-root config set WP_CACHE true --raw\""
        WOShellExec.cmd_exec(controller, cmd)


def _normalise_template_source(entry, entry_type, index):
    source = entry.get('slug') or entry.get('url')
    if not source:
        raise SiteError(
            f"WordPress template {entry_type} entry at index {index} must define a 'slug' or 'url'.")
    label = entry.get('slug') or entry.get('url')
    return source, label


def _extract_bool(entry, key, *, default=None, section="WordPress template"):
    if key not in entry:
        return default
    value = entry[key]
    if isinstance(value, bool):
        return value
    raise SiteError(f"{section} field '{key}' must be a boolean value.")


def _validate_template_map(value, section_name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SiteError(f"WordPress template '{section_name}' must be a JSON object.")
    return value


def load_wp_template(controller, template_path):
    """Load and validate a WordPress provisioning template from JSON."""
    resolved_path = os.path.abspath(os.path.expanduser(template_path))

    if not os.path.isfile(resolved_path):
        raise SiteError(f"WordPress template file '{resolved_path}' does not exist.")

    try:
        with open(resolved_path, 'r', encoding='utf-8') as handler:
            payload = json.load(handler)
    except (OSError, ValueError) as e:
        Log.debug(controller, str(e))
        raise SiteError("Unable to load WordPress template JSON file.")

    if not isinstance(payload, dict):
        raise SiteError("WordPress template must be a JSON object at the top level.")

    template = {
        'themes': [],
        'plugins': [],
        'options': _validate_template_map(payload.get('options'), 'options'),
        'constants': _validate_template_map(payload.get('constants'), 'constants')
    }

    themes = payload.get('themes', [])
    if themes:
        if not isinstance(themes, list):
            raise SiteError("WordPress template 'themes' must be an array.")
        for index, entry in enumerate(themes):
            if not isinstance(entry, dict):
                raise SiteError(
                    f"WordPress template theme entry at index {index} must be a JSON object.")
            source, label = _normalise_template_source(entry, 'theme', index)
            theme_data = {
                'source': source,
                'label': label,
                'activate': _extract_bool(entry, 'activate', default=False,
                                          section="WordPress template theme"),
                'network': _extract_bool(entry, 'network', default=None,
                                         section="WordPress template theme")
            }
            template['themes'].append(theme_data)

    plugins = payload.get('plugins', [])
    if plugins:
        if not isinstance(plugins, list):
            raise SiteError("WordPress template 'plugins' must be an array.")
        for index, entry in enumerate(plugins):
            if not isinstance(entry, dict):
                raise SiteError(
                    f"WordPress template plugin entry at index {index} must be a JSON object.")
            source, label = _normalise_template_source(entry, 'plugin', index)
            plugin_options = entry.get('options', {})
            if 'options' in entry and not isinstance(plugin_options, dict):
                raise SiteError(
                    f"WordPress template plugin 'options' at index {index} must be a JSON object.")
            plugin_data = {
                'source': source,
                'label': label,
                'activate': _extract_bool(entry, 'activate', default=False,
                                          section="WordPress template plugin"),
                'network': _extract_bool(entry, 'network', default=None,
                                         section="WordPress template plugin"),
                'options': plugin_options or {}
            }
            template['plugins'].append(plugin_data)

    return template


def _generate_database_username(domain_processed, max_length=12):
    """
    Generate a unique database username based on processed domain.

    Args:
        domain_processed (str): Processed domain name
        max_length (int): Maximum length for username

    Returns:
        str: Generated username
    """
    base_name = domain_processed[:max_length]
    random_suffix = generate_random(4)  # Use our unified random generator
    return f"{base_name}{random_suffix}"


def _create_database_and_user(controller, wo_db_name, wo_db_username, wo_db_password, wo_mysql_grant_host):
    """
    Create database and user with proper error handling.

    Args:
        controller: The controller object
        wo_db_name (str): Database name
        wo_db_username (str): Username
        wo_db_password (str): Password
        wo_mysql_grant_host (str): Grant host

    Returns:
        tuple: (final_db_name, final_username)
    """
    Log.info(controller, "Setting up database\t\t", end='')
    Log.debug(controller, "Creating database {0}".format(wo_db_name))

    # Handle existing database by generating new name
    try:
        if WOMysql.check_db_exists(controller, wo_db_name):
            Log.debug(controller, "Database already exists, Updating DB_NAME .. ")
            wo_db_name = _generate_database_name(wo_db_name, 32)
            wo_db_username = _generate_database_username(wo_db_name, 12)
    except MySQLConnectionError:
        raise SiteError("MySQL Connectivity problem occured")

    # Create database
    try:
        WOMysql.execute(controller, "create database `{0}`".format(wo_db_name))
    except StatementExcecutionError:
        Log.info(controller, "[" + Log.ENDC + Log.FAIL + "Failed" + Log.OKBLUE + "]")
        raise SiteError("create database execution failed")

    # Create user
    Log.debug(controller, "Creating user {0}".format(wo_db_username))
    try:
        WOMysql.execute(controller,
                        "create user `{0}`@`{1}` identified by '{2}'"
                        .format(wo_db_username, wo_mysql_grant_host, wo_db_password),
                        log=False)
    except StatementExcecutionError:
        Log.info(controller, "[" + Log.ENDC + Log.FAIL + "Failed" + Log.OKBLUE + "]")
        raise SiteError("creating user failed for database")

    # Grant permissions
    Log.debug(controller, "Setting up user privileges")
    try:
        WOMysql.execute(controller,
                        "grant select, insert, update, delete, create, drop, "
                        "references, index, alter, create temporary tables, "
                        "lock tables, execute, create view, show view, "
                        "create routine, alter routine, event, "
                        "trigger on `{0}`.* to `{1}`@`{2}`"
                        .format(wo_db_name, wo_db_username, wo_mysql_grant_host))
    except StatementExcecutionError:
        Log.info(controller, "[" + Log.ENDC + Log.FAIL + "Failed" + Log.OKBLUE + "]")
        raise SiteError("grant privileges to user failed for database")

    return wo_db_name, wo_db_username


def setupdatabase(self, data):
    """
    Setup database for WordPress site - improved version using centralized utilities.

    Args:
        data (dict): Site configuration data

    Returns:
        dict: Updated data with database configuration
    """
    wo_domain_name = data['site_name']

    # Use our unified random generator instead of hardcoded version
    wo_random_pass = generate_random(24)  # Replaces hardcoded random generation

    # Improved domain name processing using helper function
    domain_processed = _process_domain_for_database(wo_domain_name)
    wo_replace_dot = domain_processed['dot_replaced']
    wo_replace_underscore = domain_processed['underscore_removed']

    # Centralized config parsing
    mysql_config = _get_mysql_config(self)

    wo_db_name = ''
    wo_db_username = ''
    wo_db_password = ''

    # Handle database name input
    if mysql_config['prompt_dbname']:
        try:
            wo_db_name = input('Enter the MySQL database name [{0}]: '
                               .format(wo_replace_dot))
        except EOFError:
            raise SiteError("Unable to input database name")

    if not wo_db_name:
        wo_db_name = _generate_database_name(wo_replace_dot)

    # Handle database user input
    if mysql_config['prompt_dbuser']:
        try:
            wo_db_username = input('Enter the MySQL database user name [{0}]: '
                                   .format(wo_replace_dot))
            wo_db_password = getpass.getpass(prompt='Enter the MySQL database'
                                             ' password [{0}]: '
                                             .format(wo_random_pass))
        except EOFError:
            raise SiteError("Unable to input database credentials")

    if not wo_db_username:
        wo_db_username = _generate_database_username(wo_replace_underscore)
    if not wo_db_password:
        wo_db_password = wo_random_pass

    # Use the database creation helper function
    wo_db_name, wo_db_username = _create_database_and_user(
        self, wo_db_name, wo_db_username, wo_db_password, mysql_config['grant_host'])

    Log.info(self, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")

    data['wo_db_name'] = wo_db_name
    data['wo_db_user'] = wo_db_username
    data['wo_db_pass'] = wo_db_password
    data['wo_db_host'] = WOVar.wo_mysql_host
    data['wo_mysql_grant_host'] = mysql_config['grant_host']
    return (data)


def _get_wordpress_config(controller, data):
    """
    Get WordPress configuration from app config and data with proper defaults.

    Args:
        controller: The controller object
        data (dict): Site data containing potential wp-* keys

    Returns:
        dict: WordPress configuration
    """
    # Get base config from app
    if controller.app.config.has_section('wordpress'):
        base_config = {
            'user': controller.app.config.get('wordpress', 'user'),
            'password': controller.app.config.get('wordpress', 'password'),
            'email': controller.app.config.get('wordpress', 'email'),
            'prompt_prefix': controller.app.config.get('wordpress', 'prefix') in ['True', 'true']
        }
    else:
        base_config = {
            'user': '',
            'password': '',
            'email': '',
            'prompt_prefix': False
        }

    # Override with data values if present
    if 'wp-user' in data and data['wp-user']:
        base_config['user'] = data['wp-user']
    if 'wp-email' in data and data['wp-email']:
        base_config['email'] = data['wp-email']
    if 'wp-pass' in data and data['wp-pass']:
        base_config['password'] = data['wp-pass']

    return base_config


def setupwordpress(self, data, vhostonly=False):
    """
    Setup WordPress installation - refactored for better readability and maintainability.

    Args:
        data (dict): Site configuration data
        vhostonly (bool): Whether to setup virtual host only

    Returns:
        dict: WordPress credentials (wp_user, wp_pass, wp_email)
    """
    wo_domain_name = data['site_name']
    wo_site_webroot = data['webroot']

    # Get WordPress configuration using helper
    wp_config = _get_wordpress_config(self, data)
    wo_wp_user = wp_config['user']
    wo_wp_pass = wp_config['password']
    wo_wp_email = wp_config['email']

    # Use our unified random generator for password fallback
    wo_random_pass = generate_random(24)

    # Ensure database is configured
    if not (data.get('wo_db_name') and data.get('wo_db_user') and data.get('wo_db_pass')):
        data = setupdatabase(self, data)

    # Change to htdocs directory
    WOFileUtils.chdir(self, f'{wo_site_webroot}/htdocs/')

    # Download WordPress core (if not vhost-only)
    if not vhostonly:
        _download_wordpress_core(self, wo_site_webroot)

    # Setup WordPress table prefix
    wo_wp_prefix = _setup_wp_prefix(self, wp_config['prompt_prefix'])

    # Create wp-config.php
    _create_wp_config(self, data, wo_wp_prefix, vhostonly)

    # Configure WordPress variables
    _configure_wp_variables(self, wo_domain_name)

    # Move wp-config.php outside webroot for security
    _move_wp_config(self, wo_site_webroot)

    # Handle vhost-only mode
    if vhostonly:
        WOFileUtils.chdir(self, wo_site_webroot)
        WOFileUtils.rm(self, f"{wo_site_webroot}/htdocs")
        WOFileUtils.mkdir(self, f"{wo_site_webroot}/htdocs")
        WOFileUtils.chown(self, f"{wo_site_webroot}/htdocs", 'www-data', 'www-data')
        return dict(wp_user=wo_wp_user, wp_pass=wo_wp_pass, wp_email=wo_wp_email)

    # Validate and setup WordPress credentials
    if not wo_wp_pass:
        wo_wp_pass = wo_random_pass

    wo_wp_user, wo_wp_email = _validate_wp_credentials(self, wo_wp_user, wo_wp_email)

    # Install WordPress core and setup database tables
    _install_wordpress_core(self, data, wo_wp_user, wo_wp_pass, wo_wp_email)

    # Setup permalinks
    _setup_wordpress_permalinks(self)

    # Setup cache plugins
    _setup_cache_plugins(self, data)

    apply_wp_template(self, data)

    return dict(wp_user=wo_wp_user, wp_pass=wo_wp_pass, wp_email=wo_wp_email)


def setupwordpressnetwork(self, data):
    wo_site_webroot = data['webroot']
    WOFileUtils.chdir(self, '{0}/htdocs/'.format(wo_site_webroot))
    Log.info(self, "Setting up WordPress Network \t", end='')
    try:
        if WOShellExec.cmd_exec(self, 'wp --allow-root core multisite-convert'
                                ' --title=\'{0}\' {subdomains}'
                                .format(data['www_domain'],
                                        subdomains='--subdomains'
                                        if not data['wpsubdir'] else '')):
            pass
        else:
            Log.info(self, "[" + Log.ENDC + Log.FAIL +
                     "Fail" + Log.OKBLUE + "]")
            raise SiteError("setup WordPress network failed")

    except CommandExecutionError as e:
        Log.debug(self, str(e))
        Log.info(self, "[" + Log.ENDC + Log.FAIL + "Fail" + Log.OKBLUE + "]")
        raise SiteError("setup WordPress network failed")
    Log.info(self, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")


def _execute_wp_plugin_command(controller, webroot, action, plugin_name, **options):
    """Execute WordPress plugin command with standardized error handling"""
    WOFileUtils.chdir(controller, f'{webroot}/htdocs/')

    cmd = build_wp_command(f"plugin {action}", plugin_name, **options)

    execute_command_safely(controller, cmd, f"plugin {action} failed")


def _log_plugin_operation(controller, action, plugin_name, success=True):
    """Standardized logging for plugin operations"""
    if success:
        if action == "install":
            Log.valide(controller, f"Installing plugin {plugin_name}")
        elif action == "uninstall":
            Log.valide(controller, f"Uninstalling plugin {plugin_name}")
        else:
            Log.valide(controller, f"Setting plugin {plugin_name}")
    else:
        if action == "install":
            Log.failed(controller, f"Installing plugin {plugin_name}")
        elif action == "uninstall":
            Log.failed(controller, f"Uninstalling plugin {plugin_name}")
        else:
            Log.failed(controller, f"Setting plugin {plugin_name}")


def _execute_wp_theme_command(controller, webroot, action, theme_name, **options):
    """Execute WordPress theme command with standardized error handling"""
    WOFileUtils.chdir(controller, f'{webroot}/htdocs/')

    cmd = build_wp_command(f"theme {action}", theme_name, **options)
    execute_command_safely(controller, cmd, f"theme {action} failed")


def _log_theme_operation(controller, action, theme_name, success=True):
    """Standardized logging for theme operations"""
    message = f"{action.capitalize()} theme {theme_name}"
    if success:
        Log.valide(controller, message)
    else:
        Log.failed(controller, message)


def _serialise_wp_option_value(value):
    """Serialise option values for WP-CLI commands."""
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)


def installwp_theme(self, theme_name, data, activate=False, network=None):
    """Install and optionally activate a WordPress theme."""
    webroot = data['webroot']
    Log.wait(self, f"Installing theme {theme_name}")

    try:
        _execute_wp_theme_command(self, webroot, "install", theme_name)

        if data.get('multisite'):
            enable_kwargs = {}
            if network is True:
                enable_kwargs['network'] = True
            _execute_wp_theme_command(self, webroot, "enable", theme_name, **enable_kwargs)

        if activate:
            _execute_wp_theme_command(self, webroot, "activate", theme_name)

        _log_theme_operation(self, "install", theme_name, success=True)
    except SiteError as e:
        _log_theme_operation(self, "install", theme_name, success=False)
        raise e


def installwp_plugin(self, plugin_name, data, activate=True, network=None):
    """
    Install and activate WordPress plugin - refactored for better maintainability.

    Args:
        plugin_name (str): Name of the plugin to install
        data (dict): Site data containing webroot and multisite info
    """
    webroot = data['webroot']
    Log.wait(self, f"Installing plugin {plugin_name}")

    try:
        # Install plugin
        _execute_wp_plugin_command(self, webroot, "install", plugin_name)

        # Activate plugin (with network flag for multisite)
        if activate:
            activation_kwargs = {}
            network_flag = data.get('multisite') if network is None else network
            if network_flag:
                activation_kwargs['network'] = True
            _execute_wp_plugin_command(self, webroot, "activate", plugin_name, **activation_kwargs)

        _log_plugin_operation(self, "install", plugin_name, success=True)
        return 1
    except SiteError as e:
        _log_plugin_operation(self, "install", plugin_name, success=False)
        raise e


def uninstallwp_plugin(self, plugin_name, data):
    """
    Deactivate and uninstall WordPress plugin - refactored for better maintainability.

    Args:
        plugin_name (str): Name of the plugin to uninstall
        data (dict): Site data containing webroot info
    """
    webroot = data['webroot']
    Log.debug(self, f"Uninstalling plugin {plugin_name}, please wait...")
    Log.wait(self, f"Uninstalling plugin {plugin_name}")

    try:
        # Deactivate plugin
        _execute_wp_plugin_command(self, webroot, "deactivate", plugin_name)

        # Uninstall plugin
        _execute_wp_plugin_command(self, webroot, "uninstall", plugin_name)

        _log_plugin_operation(self, "uninstall", plugin_name, success=True)
    except SiteError as e:
        _log_plugin_operation(self, "uninstall", plugin_name, success=False)
        raise e


def setupwp_plugin(self, plugin_name, plugin_option, plugin_data, data):
    """
    Configure WordPress plugin settings - refactored for better maintainability.

    Args:
        plugin_name (str): Name of the plugin to configure
        plugin_option (str): Option name to update
        plugin_data (str): JSON data for the option
        data (dict): Site data containing webroot and multisite info
    """
    webroot = data['webroot']
    Log.wait(self, f"Setting plugin {plugin_name}")
    WOFileUtils.chdir(self, f'{webroot}/htdocs/')

    try:
        if data.get('multisite'):
            # Multisite: use network meta update
            cmd = build_wp_command("network meta update", "1", plugin_option, plugin_data)
        else:
            # Single site: use option update
            cmd = build_wp_command("option update", plugin_option, plugin_data)

        execute_command_safely(self, cmd, "plugin setup failed")
        _log_plugin_operation(self, "setup", plugin_name, success=True)

    except SiteError as e:
        _log_plugin_operation(self, "setup", plugin_name, success=False)
        raise e


def update_wp_options(self, options, data):
    """Update WordPress options using WP-CLI."""
    if not options:
        return

    webroot = data['webroot']
    WOFileUtils.chdir(self, f'{webroot}/htdocs/')

    for option_name, option_value in options.items():
        Log.wait(self, f"Updating WordPress option {option_name}")
        option_payload = _serialise_wp_option_value(option_value)
        cmd = build_wp_command("option update", option_name, option_payload)
        execute_command_safely(self, cmd, f"updating option {option_name} failed")
        Log.valide(self, f"Updating WordPress option {option_name}")


def define_wp_constants(self, constants, data):
    """Define constants in wp-config.php via WP-CLI."""
    if not constants:
        return

    webroot = data['webroot']
    WOFileUtils.chdir(self, f'{webroot}/htdocs/')

    for constant_name, constant_value in constants.items():
        Log.wait(self, f"Defining WordPress constant {constant_name}")
        if isinstance(constant_value, bool):
            value = 'true' if constant_value else 'false'
            cmd = build_wp_command("config set", constant_name, value, raw=True)
        elif isinstance(constant_value, (int, float)):
            cmd = build_wp_command("config set", constant_name, constant_value, raw=True)
        else:
            cmd = build_wp_command("config set", constant_name, str(constant_value))
        execute_command_safely(self, cmd, f"defining constant {constant_name} failed")
        Log.valide(self, f"Defining WordPress constant {constant_name}")


def apply_wp_template(self, data):
    """Apply the loaded WordPress template after core installation."""
    template = data.get('wp_template')
    if not template:
        return

    themes = template.get('themes', [])
    for theme in themes:
        installwp_theme(self, theme['source'], data,
                        activate=theme.get('activate', False),
                        network=theme.get('network'))

    plugins = template.get('plugins', [])
    for plugin in plugins:
        installwp_plugin(self, plugin['source'], data,
                         activate=plugin.get('activate', False),
                         network=plugin.get('network'))
        for option_name, option_value in plugin.get('options', {}).items():
            plugin_payload = _serialise_wp_option_value(option_value)
            setupwp_plugin(self, plugin['label'], option_name, plugin_payload, data)

    update_wp_options(self, template.get('options'), data)
    define_wp_constants(self, template.get('constants'), data)


def parse_wp_db_config(config_path):
    """
    Parse WordPress database configuration from wp-config.php file.

    Args:
        config_path (str): Path to wp-config.php file

    Returns:
        dict: Database credentials (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST)
    """
    creds = {}
    if not os.path.isfile(config_path):
        return creds

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'DB_NAME' in line and "'" in line:
                    parts = line.split("'")
                    if len(parts) >= 4:
                        creds['DB_NAME'] = parts[3]
                elif 'DB_USER' in line and "'" in line:
                    parts = line.split("'")
                    if len(parts) >= 4:
                        creds['DB_USER'] = parts[3]
                elif 'DB_PASSWORD' in line and "'" in line:
                    parts = line.split("'")
                    if len(parts) >= 4:
                        creds['DB_PASSWORD'] = parts[3]
                elif 'DB_HOST' in line and "'" in line:
                    parts = line.split("'")
                    if len(parts) >= 4:
                        creds['DB_HOST'] = parts[3]
    except (IOError, UnicodeDecodeError) as e:
        # Return empty dict if file cannot be read
        return {}

    return creds


def copy_nginx_acl_files(controller, src_slug, dest_slug, base_path='/etc/nginx/acl'):
    """
    Copy nginx ACL files from source to destination site.

    Args:
        controller: Controller instance for file operations
        src_slug (str): Source site slug
        dest_slug (str): Destination site slug
        base_path (str): Base ACL directory path
    """
    src_acl = os.path.join(base_path, src_slug)
    dest_acl = os.path.join(base_path, dest_slug)

    if not os.path.isdir(src_acl):
        return

    try:
        # Ensure base directory exists
        os.makedirs(base_path, exist_ok=True)

        # Remove existing destination if it exists
        if os.path.exists(dest_acl):
            WOFileUtils.rm(controller, dest_acl)

        # Copy ACL files
        WOFileUtils.copyfiles(controller, src_acl, dest_acl)

        # Update protected.conf file if it exists
        protected_file = os.path.join(dest_acl, 'protected.conf')
        if os.path.isfile(protected_file):
            with open(protected_file, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace(src_slug, dest_slug)
            with open(protected_file, 'w', encoding='utf-8') as f:
                f.write(content)

        Log.debug(controller, f"Copied ACL files from {src_acl} to {dest_acl}")

    except Exception as e:
        Log.debug(controller, f"Failed to copy ACL files: {str(e)}")


def extract_site_backup(controller, backup_path):
    """
    Extract site backup archive to temporary directory.

    Args:
        controller: Controller instance
        backup_path (str): Path to backup archive

    Returns:
        str: Path to extracted backup directory
    """
    import tempfile

    # If already a directory, return as-is
    if os.path.isdir(backup_path):
        return backup_path

    if not os.path.isfile(backup_path):
        raise SiteError(f"Backup file not found: {backup_path}")

    # Create temporary directory for extraction
    temp_dir = tempfile.mkdtemp(prefix='wo-restore-')

    try:
        # Handle zstd compressed archives specifically for WordOps
        if backup_path.endswith('.tar.zst'):
            cmd = f"tar --zstd -xf '{backup_path}' -C '{temp_dir}'"
        elif backup_path.endswith('.tar.gz') or backup_path.endswith('.tgz'):
            cmd = f"tar -xzf '{backup_path}' -C '{temp_dir}'"
        elif backup_path.endswith('.tar'):
            cmd = f"tar -xf '{backup_path}' -C '{temp_dir}'"
        elif backup_path.endswith('.zip'):
            cmd = f"unzip -q '{backup_path}' -d '{temp_dir}'"
        else:
            # Try zstd extraction as default for WordOps
            cmd = f"tar --zstd -xf '{backup_path}' -C '{temp_dir}'"

        try:
            execute_command_safely(controller, cmd, f"Failed to extract backup: {backup_path}")
        except SiteError:
            Log.error(controller, 'failed to extract backup archive')

        # Check extracted contents
        entries = os.listdir(temp_dir)
        if not entries:
            Log.error(controller, 'invalid backup archive')

        # Return path to first entry (backup directory)
        extracted_path = os.path.join(temp_dir, entries[0])
        return extracted_path

    except Exception as e:
        # Cleanup on failure
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise SiteError(f"Backup extraction failed: {str(e)}")


def restore_database_from_dump(controller, dump_file, db_meta):
    """
    Restore database from SQL dump file with user/database creation.

    Args:
        controller: Controller instance
        dump_file (str): Path to SQL dump file
        db_meta (dict): Database metadata (name, user, password, host, etc.)
    """
    # Extract database credentials from metadata
    db_name = db_meta.get('db_name')
    db_user = db_meta.get('db_user')
    db_pass = db_meta.get('db_password')
    db_host = db_meta.get('db_host', 'localhost')

    # Skip if no database name or dump file doesn't exist
    if not db_name or not os.path.isfile(dump_file):
        return

    try:
        from wo.core.mysql import MySQLConnectionError, StatementExcecutionError, WOMysql

        # Create database if it doesn't exist
        WOMysql.execute(controller, f"CREATE DATABASE IF NOT EXISTS `{db_name}`")

        # Create user and grant privileges if user is specified
        if db_user:
            WOMysql.execute(
                controller,
                f"CREATE USER IF NOT EXISTS `{db_user}`@`{db_host}` IDENTIFIED BY '{db_pass}'",
                log=False,
            )
            WOMysql.execute(
                controller,
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{db_user}`@`{db_host}`",
                log=False,
            )

        # Import the SQL dump
        cmd = f'mariadb {db_name} < {dump_file}'
        execute_command_safely(controller, cmd, "Database restoration failed", log_command=False)

        Log.info(controller, "Database restored successfully")

    except (MySQLConnectionError, StatementExcecutionError, SiteError) as e:
        Log.debug(controller, str(e))
        Log.warn(controller, 'Failed to restore database')


def build_clone_site_data(src_info, src_domain, dest_domain, wp_credentials, dest_type='domain'):
    """
    Build site data configuration for cloning.

    Args:
        src_info: Source site information object
        src_domain (str): Source domain name
        dest_domain (str): Destination domain name
        wp_credentials (dict): WordPress admin credentials
        dest_type (str): Destination domain type (domain/subdomain)

    Returns:
        dict: Complete site configuration data
    """
    dest_webroot = os.path.join(WOVar.wo_webroot, dest_domain)
    php_key = f"php{src_info.php_version}".replace('.', '')
    www_domain = f"www.{dest_domain}" if dest_type != 'subdomain' else ''

    # Base configuration
    data = {
        'site_name': dest_domain,
        'www_domain': www_domain,
        'webroot': dest_webroot,
        'static': False,
        'basic': True,
        'wp': False,
        'wpfc': False,
        'wpsc': False,
        'wprocket': False,
        'wpce': False,
        'wpredis': False,
        'multisite': False,
        'wpsubdir': False,
        'wo_php': php_key,
        'pool_name': dest_domain.replace('.', '-').lower(),
        'php_ver': php_key.replace('php', ''),
        'php_fpm_user': f"php-{dest_domain.replace('.', '-').lower()}",
    }

    # Add WordPress credentials
    data.update(wp_credentials)

    # Configure site type and caching based on source
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

    return data


def clone_database(controller, src_domain, src_db_config, dest_db_config):
    """
    Clone database from source to destination site.

    Args:
        controller: Controller instance
        src_domain (str): Source domain name
        src_db_config (dict): Source database configuration
        dest_db_config (dict): Destination database configuration
    """
    if not src_db_config.get('DB_NAME'):
        Log.info(controller, "No source database found to clone")
        return

    # Create temporary backup file
    backup_file = f"/tmp/{src_domain.replace('.', '_')}.sql"

    try:
        # Dump source database
        dump_cmd = (
            f"mariadb-dump --defaults-extra-file=/etc/mysql/conf.d/my.cnf "
            f"--single-transaction --quick --add-drop-table --hex-blob "
            f"{src_db_config['DB_NAME']} > {backup_file}"
        )
        execute_command_safely(controller, dump_cmd, "Failed to dump source database")

        # Import to destination database
        import_cmd = (
            f"mariadb --defaults-extra-file=/etc/mysql/conf.d/my.cnf "
            f"{dest_db_config['DB_NAME']} < {backup_file}"
        )
        execute_command_safely(controller, import_cmd, "Failed to import database to destination")

        Log.info(controller, "Database cloned successfully")

    finally:
        # Clean up temporary backup file
        if os.path.exists(backup_file):
            WOFileUtils.rm(controller, backup_file)


def clone_website_files(controller, src_domain, dest_domain):
    """
    Clone website files from source to destination.

    Args:
        controller: Controller instance
        src_domain (str): Source domain name
        dest_domain (str): Destination domain name
    """
    src_root = os.path.join(WOVar.wo_webroot, src_domain, 'htdocs')
    dest_root = os.path.join(WOVar.wo_webroot, dest_domain, 'htdocs')

    if not os.path.exists(src_root):
        raise SiteError(f"Source website files not found: {src_root}")

    Log.info(controller, f"Copying website files from {src_domain} to {dest_domain}")
    WOFileUtils.copyfiles(controller, src_root, dest_root, overwrite=True)


def update_wordpress_urls(controller, src_domain, dest_domain, dest_webroot):
    """
    Update WordPress URLs in database using WP-CLI.

    Args:
        controller: Controller instance
        src_domain (str): Source domain name
        dest_domain (str): Destination domain name
        dest_webroot (str): Destination webroot path
    """
    dest_htdocs = os.path.join(dest_webroot, 'htdocs')

    if not os.path.exists(dest_htdocs):
        raise SiteError(f"Destination htdocs not found: {dest_htdocs}")

    Log.info(controller, f"Updating WordPress URLs from {src_domain} to {dest_domain}")
    cmd = f"{WOVar.wo_wpcli_path} search-replace {src_domain} {dest_domain} --path={dest_htdocs} --all-tables --allow-root"
    execute_command_safely(controller, cmd, "Failed to update WordPress URLs")


def generate_wp_config_for_clone(controller, data):
    """
    Generate ONLY wp-config.php for cloned sites without affecting existing files.

    Args:
        controller: Controller instance
        data (dict): Site configuration data with database credentials

    Returns:
        str: Path to generated wp-config.php
    """
    domain_name = data['site_name']
    webroot = data['webroot']

    # Get WordPress configuration
    wp_config = _get_wordpress_config(controller, data)

    # Use default prefix for cloned sites (we don't prompt for clones)
    wp_prefix = SITE_CONSTANTS['DEFAULT_WP_PREFIX']

    # Change to htdocs directory (should already exist with cloned files)
    htdocs_path = f'{webroot}/htdocs/'
    if not os.path.exists(htdocs_path):
        raise SiteError(f"Cloned WordPress files not found: {htdocs_path}")

    WOFileUtils.chdir(controller, htdocs_path)

    # Create wp-config.php with destination database credentials
    _create_wp_config(controller, data, wp_prefix, vhostonly=False)  # Don't use vhostonly

    # Configure WordPress variables for the new domain
    _configure_wp_variables(controller, domain_name)

    # Move wp-config.php outside webroot for security
    _move_wp_config(controller, webroot)

    config_path = os.path.join(webroot, 'wp-config.php')
    Log.info(controller, f"Generated wp-config.php for cloned site: {domain_name}")

    return config_path


def safe_site_backup_for_update(controller, data):
    """
    Create a safe backup for site updates that preserves original files.

    Args:
        controller: Controller instance
        data (dict): Site data

    Returns:
        str: Backup path for rollback if needed
    """
    try:
        # Create backup with COPY (not move) to preserve original files
        sitebackup(controller, data, move_files=False, db_only=False, files_only=False)
        backup_path = f"{data['webroot']}/backup/{WOVar.wo_date}"
        Log.info(controller, f"Safe backup created at: {backup_path}")
        return backup_path
    except Exception as e:
        Log.debug(controller, str(e))
        raise SiteError(f"Failed to create backup before update: {str(e)}")


def rollback_site_from_backup(controller, data, backup_path):
    """
    Rollback site from backup on update failure.

    Args:
        controller: Controller instance
        data (dict): Site data
        backup_path (str): Path to backup directory
    """
    try:
        if not os.path.exists(backup_path):
            Log.warn(controller, f"Backup path not found: {backup_path}")
            return

        webroot = data['webroot']
        htdocs_backup = os.path.join(backup_path, 'htdocs')
        htdocs_current = os.path.join(webroot, 'htdocs')

        if os.path.exists(htdocs_backup):
            # Remove current broken htdocs
            if os.path.exists(htdocs_current):
                WOFileUtils.rm(controller, htdocs_current)

            # Restore from backup
            WOFileUtils.copyfiles(controller, htdocs_backup, htdocs_current)
            Log.info(controller, "Site files restored from backup")

        # Look for wp-config.php in backup
        config_backup = os.path.join(backup_path, 'wp-config.php')
        config_current = os.path.join(webroot, 'wp-config.php')

        if os.path.exists(config_backup):
            WOFileUtils.copyfile(controller, config_backup, config_current)
            Log.info(controller, "wp-config.php restored from backup")

    except Exception as e:
        Log.debug(controller, str(e))
        Log.error(controller, f"Failed to rollback from backup: {str(e)}")


def setwebrootpermissions(self, webroot, user=WOVar.wo_php_user):
    Log.debug(self, "Setting up permissions")
    try:
        WOFileUtils.findBrokenSymlink(self, f'{webroot}')
        WOFileUtils.chown(self, webroot, user,
                          user, recursive=True)
    except Exception as e:
        Log.debug(self, str(e))
        raise SiteError("problem occured while setting up webroot permissions")


def sitebackup(self, data, move_files=True, db_only=False, files_only=False):
    """Backup a site and optionally move webroot/config files.

    ``move_files`` controls whether WordPress "htdocs" and configuration
    files are moved into the backup directory instead of copied.  This is
    used by ``wo site update`` which expects the original webroot to be
    removed so a fresh one can be created.  ``wo site backup`` passes
    ``move_files=False`` to keep the live site untouched.

    ``db_only`` and ``files_only`` limit the backup to the selected type of
    data.
    """
    wo_site_webroot = data['webroot']
    backup_path = wo_site_webroot + '/backup/{0}'.format(WOVar.wo_date)
    if not WOFileUtils.isexist(self, backup_path):
        WOFileUtils.mkdir(self, backup_path)
    Log.info(self, "Backup location : {0}".format(backup_path))
    WOFileUtils.copyfile(self, '/etc/nginx/sites-available/{0}'
                         .format(data['site_name']), backup_path)

    # Use centralized PHP version management instead of hardcoded list
    backup_site_types = ['html', 'php', 'proxy', 'mysql'] + PHPVersionManager.SUPPORTED_VERSIONS + ['php72', 'php73']  # Legacy versions
    if not db_only and data['currsitetype'] in backup_site_types:
        Log.info(self, "Backing up Webroot \t\t", end='')
        src = os.path.join(wo_site_webroot, 'htdocs')
        dst = backup_path if move_files and data['wp'] else os.path.join(backup_path, 'htdocs')
        if data['wp'] and move_files:
            WOFileUtils.mvfile(self, src, dst)
        else:
            WOFileUtils.copyfiles(self, src, dst)
        Log.info(self, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")

    configfiles = glob.glob(wo_site_webroot + '/*-config.php')
    if not configfiles:
        Log.debug(self, "Config files not found in {0}/ "
                  .format(wo_site_webroot))
        if data['currsitetype'] not in ['mysql']:
            Log.debug(self, "Searching wp-config.php in {0}/htdocs/ "
                      .format(wo_site_webroot))
            configfiles = glob.glob(wo_site_webroot + '/htdocs/wp-config.php')

    if data['wo_db_name'] and not files_only:
        Log.info(self, 'Backing up database \t\t', end='')
        try:
            if not WOShellExec.cmd_exec(
                self, "mysqldump --single-transaction --hex-blob "
                "{0} | zstd -c > {1}/{0}.zst"
                .format(data['wo_db_name'],
                        backup_path)):
                Log.info(self,
                         "[" + Log.ENDC + Log.FAIL + "Fail" + Log.OKBLUE + "]")
                raise SiteError("mysqldump failed to backup database")
        except CommandExecutionError as e:
            Log.debug(self, str(e))
            Log.info(self, "[" + Log.ENDC + "Fail" + Log.OKBLUE + "]")
            raise SiteError("mysqldump failed to backup database")
        Log.info(self, "[" + Log.ENDC + "Done" + Log.OKBLUE + "]")

    if configfiles:
        if data['currsitetype'] in ['mysql', 'proxy']:
            if data.get('php73') is True and not data['wp']:
                WOFileUtils.copyfile(self, configfiles[0], backup_path)
            else:
                if move_files and not db_only:
                    WOFileUtils.mvfile(self, configfiles[0], backup_path)
                else:
                    WOFileUtils.copyfile(self, configfiles[0], backup_path)
        else:
            WOFileUtils.copyfile(self, configfiles[0], backup_path)


def site_package_check(self, stype):
    apt_packages = []
    packages = []
    stack = WOStackController()
    stack.app = self.app
    pargs = self.app.pargs
    if stype in ['html', 'proxy', 'php', 'mysql', 'wp', 'wpsubdir',
                 'wpsubdomain', 'php74', 'php80', 'php81', 'php82', 'php83', 'php84', 'alias', 'subsite']:
        Log.debug(self, "Setting apt_packages variable for Nginx")

        # Check if server has nginx-custom package
        if not (WOAptGet.is_installed(self, 'nginx-custom') or
                WOAptGet.is_installed(self, 'nginx-mainline')):
            # check if Server has nginx-plus installed
            if WOAptGet.is_installed(self, 'nginx-plus'):
                # do something
                # do post nginx installation configuration
                Log.info(self, "NGINX PLUS Detected ...")
                apt = ["nginx-plus"] + WOVar.wo_nginx
                # apt_packages = apt_packages + WOVar.wo_nginx
                post_pref(self, apt, packages)
            elif WOAptGet.is_installed(self, 'nginx'):
                Log.info(self, "WordOps detected a previously"
                               "installed Nginx package. "
                               "It may or may not have required modules. "
                               "\nIf you need help, please create an issue at "
                               "https://github.com/WordOps/WordOps/issues/ \n")
                apt = ["nginx"] + WOVar.wo_nginx
                # apt_packages = apt_packages + WOVar.wo_nginx
                post_pref(self, apt, packages)
            elif os.path.isfile('/usr/sbin/nginx'):
                post_pref(self, WOVar.wo_nginx, [])
            else:
                apt_packages = apt_packages + WOVar.wo_nginx
        else:
            # Fix for Nginx white screen death
            if not WOFileUtils.grep(self, '/etc/nginx/fastcgi_params',
                                    'SCRIPT_FILENAME'):
                with open('/etc/nginx/fastcgi_params', encoding='utf-8',
                          mode='a') as wo_nginx:
                    wo_nginx.write('fastcgi_param \tSCRIPT_FILENAME '
                                   '\t$request_filename;\n')

        # Use centralized PHP version management
        try:
            PHPVersionManager.validate_single_version(pargs)
        except SiteError as e:
            Log.error(self, str(e))

    if (not PHPVersionManager.has_any_php_version(pargs) and
        stype in ['php', 'mysql', 'wp', 'wpsubdir', 'wpsubdomain']):
        Log.debug(self, "Setting apt_packages variable for PHP")

        for version_key, version_number in WOVar.wo_php_versions.items():
            if (self.app.config.has_section('php') and
                    self.app.config.get('php', 'version') == version_number):
                Log.debug(
                    self,
                    f"Setting apt_packages variable for PHP {version_number}")
                if not WOAptGet.is_installed(self, f'php{version_number}-fpm'):
                    apt_packages += getattr(
                        WOVar, f'wo_{version_key}') + WOVar.wo_php_extra

    for version_key, version_number in WOVar.wo_php_versions.items():
        if getattr(pargs, version_key) and stype in [version_key, 'mysql', 'wp', 'wpsubdir', 'wpsubdomain']:
            Log.debug(self, f"Setting apt_packages variable for PHP {version_number}")
            if not WOAptGet.is_installed(self, f'php{version_number}-fpm'):
                apt_packages += getattr(WOVar, f'wo_{version_key}') + WOVar.wo_php_extra

    if stype in ['mysql', 'wp', 'wpsubdir', 'wpsubdomain']:
        Log.debug(self, "Setting apt_packages variable for MySQL")
        if not WOMysql.mariadb_ping(self):
            apt_packages = apt_packages + WOVar.wo_mysql

    if stype in ['wp', 'wpsubdir', 'wpsubdomain']:
        Log.debug(self, "Setting packages variable for WP-CLI")
        if not WOAptGet.is_exec(self, "wp"):
            packages = packages + [[f"{WOVar.wpcli_url}",
                                    "/usr/local/bin/wp", "WP-CLI"]]
    if pargs.wpredis:
        Log.debug(self, "Setting apt_packages variable for redis")
        if not WOAptGet.is_installed(self, 'redis-server'):
            apt_packages = apt_packages + WOVar.wo_redis

    if pargs.ngxblocker:
        if not os.path.isdir('/etc/nginx/bots.d'):
            Log.debug(self, "Setting packages variable for ngxblocker")
            packages = packages + \
                [["https://raw.githubusercontent.com/"
                  "mitchellkrogza/nginx-ultimate-bad-bot-blocker"
                  "/master/install-ngxblocker",
                  "/usr/local/sbin/install-ngxblocker",
                  "ngxblocker"]]

    return (stack.install(apt_packages=apt_packages, packages=packages,
                          disp_msg=False))


def _validate_wordpress_installation(controller, domain, webroot):
    """Check if site is a valid WordPress installation"""
    WOFileUtils.chdir(controller, f'{webroot}/htdocs/')
    cmd = build_wp_command("core is-installed")

    if not execute_command_safely(controller, cmd, f"{domain} does not seem to be a WordPress site", log_command=False):
        Log.error(controller, f"{domain} does not seem to be a WordPress site")


def _get_wordpress_username(controller):
    """Get WordPress username from user input with help option"""
    try:
        wp_user = input("Provide WordPress user name [admin]: ")
    except Exception as e:
        Log.debug(controller, str(e))
        Log.error(controller, "\nCould not update password")

    # Handle help request
    if wp_user == "?":
        Log.info(controller, "Fetching WordPress user list")
        list_cmd = build_wp_command("user list", "--fields=user_login") + " | grep -v user_login"
        execute_command_safely(controller, list_cmd, "fetch wp userlist command failed")

    return wp_user or SITE_CONSTANTS['DEFAULT_WP_USER']


def _verify_wordpress_user_exists(controller, username):
    """Verify if WordPress user exists"""
    check_cmd = build_wp_command("user list", "--fields=user_login") + f" | grep {username}$"
    try:
        return WOShellExec.cmd_exec(controller, check_cmd)
    except CommandExecutionError as e:
        Log.debug(controller, str(e))
        raise SiteError("WordPress user existence check failed")


def _get_user_password(controller, username):
    """Get password from user input with validation"""
    try:
        password = getpass.getpass(prompt=f"Provide password for {username} user: ")

        while not password:
            password = getpass.getpass(prompt=f"Provide password for {username} user: ")

        return password
    except Exception as e:
        Log.debug(controller, str(e))
        raise SiteError("failed to read password input")


def _update_wordpress_user_password(controller, username, password):
    """Update WordPress user password"""
    update_cmd = build_wp_command("user update", username, user_pass=password)
    execute_command_safely(controller, update_cmd, "wp user password update command failed")


def updatewpuserpassword(self, wo_domain, wo_site_webroot):
    """
    Update WordPress user password - refactored for better maintainability.

    Args:
        wo_domain (str): WordPress domain name
        wo_site_webroot (str): Site webroot path
    """
    # Validate WordPress installation
    _validate_wordpress_installation(self, wo_domain, wo_site_webroot)

    # Get username from user input
    wp_user = _get_wordpress_username(self)

    # Verify user exists
    if _verify_wordpress_user_exists(self, wp_user):
        # Get new password
        wp_password = _get_user_password(self, wp_user)

        # Update password
        _update_wordpress_user_password(self, wp_user, wp_password)

        Log.info(self, "Password updated successfully")
    else:
        Log.error(self, f"Invalid WordPress user {wp_user} for {wo_domain}.")


def display_cache_settings(self, data):
    if data['wpsc']:
        if data['multisite']:
            Log.info(self, "Configure WPSC:"
                     "\t\thttp://{0}/wp-admin/network/settings.php?"
                     "page=wpsupercache"
                     .format(data['site_name']))
        else:
            Log.info(self, "Configure WPSC:"
                     "\t\thttp://{0}/wp-admin/options-general.php?"
                     "page=wpsupercache"
                     .format(data['site_name']))

    if data['wpredis']:
        if data['multisite']:
            Log.info(self, "Configure redis-cache:"
                     "\thttp://{0}/wp-admin/network/settings.php?"
                     "page=redis-cache".format(data['site_name']))
        else:
            Log.info(self, "Configure redis-cache:"
                     "\thttp://{0}/wp-admin/options-general.php?"
                     "page=redis-cache".format(data['site_name']))
        Log.info(self, "Object Cache:\t\tEnable")

    if data['wpfc']:
        if data['multisite']:
            Log.info(self, "Nginx-Helper configuration :"
                     "\thttp://{0}/wp-admin/network/settings.php?"
                     "page=nginx".format(data['site_name']))
        else:
            Log.info(self, "Nginx-Helper configuration :"
                     "\thttp://{0}/wp-admin/options-general.php?"
                     "page=nginx".format(data['site_name']))

    if data['wpce']:
        if data['multisite']:
            Log.info(self, "Cache-Enabler configuration :"
                     "\thttp://{0}/wp-admin/network/settings.php?"
                     "page=cache-enabler".format(data['site_name']))
        else:
            Log.info(self, "Cache-Enabler configuration :"
                     "\thttp://{0}/wp-admin/options-general.php?"
                     "page=cache-enabler".format(data['site_name']))


def logwatch(self, logfiles):
    import zlib
    import base64
    import time
    from wo.core.logwatch import LogWatcher

    def callback(filename, lines):
        for line in lines:
            if line.find(':::') == -1:
                print(line)
            else:
                data = line.split(':::')
                try:
                    decoded = base64.b64decode(data[2])
                    text = zlib.decompress(decoded).decode('utf-8', 'replace')
                    print(data[0], data[1], text)
                except Exception as e:
                    Log.debug(self, str(e))
                    Log.info(time.time(),
                             'caught exception rendering a new log line in %s'
                             % filename)

    logl = LogWatcher(logfiles, callback)
    logl.loop()


def detSitePar(opts):
    """
    Refactored site parameter detection - eliminates 200+ lines of duplicate code.
    Takes dictionary of parsed arguments:
    1. Returns sitetype and cachetype
    2. Raises RuntimeError when wrong combination is used like "--wp --wpsubdir" or "--html --wp"
    """
    # Use centralized PHP version management
    TYPE_OPTIONS = ['html', 'php', 'mysql', 'wp', 'wpsubdir', 'wpsubdomain'] + PHPVersionManager.SUPPORTED_VERSIONS
    CACHE_OPTIONS = ['wpfc', 'wpsc', 'wpredis', 'wprocket', 'wpce']

    # Extract enabled options
    typelist = [key for key, val in opts.items() if val and key in TYPE_OPTIONS]
    cachelist = [key for key, val in opts.items() if val and key in CACHE_OPTIONS]

    # Validate cache options (only one allowed)
    if len(cachelist) > 1:
        raise RuntimeError("Could not determine cache type. Multiple cache parameter entered")

    # Determine cache type
    cachetype = cachelist[0] if cachelist else 'basic'

    # Handle single type or no type cases
    if len(typelist) <= 1:
        return _handle_single_type(typelist, cachetype)

    # Handle multiple types - this is where all the duplication was
    return _handle_multiple_types(typelist, cachetype)


def _handle_single_type(typelist, cachetype):
    """Handle cases with 0 or 1 type options"""
    if not typelist:
        if cachetype == 'basic':
            return (None, None)
        else:
            # Cache option specified without type defaults to WordPress
            return ('wp', cachetype)

    # Single type specified
    sitetype = typelist[0]

    # PHP version alone with cache defaults to WordPress
    if PHPVersionManager.is_php_version(sitetype) and cachetype != 'basic':
        return ('wp', cachetype)

    return (sitetype, cachetype)


def _handle_multiple_types(typelist, cachetype):
    """Handle cases with multiple type options using lookup tables instead of massive if-elif chains"""

    # Define valid combinations and their resulting site types
    # This replaces 200+ lines of identical if-elif statements
    combinations = [
        # MySQL combinations (php + mysql + html = mysql)
        (['php', 'mysql', 'html'], 'mysql'),
        (['html', 'mysql'], 'mysql'),
        (['php', 'mysql'], 'mysql'),
        (['php', 'html'], 'php'),

        # WordPress combinations
        (['wp', 'wpsubdir'], 'wpsubdir'),
        (['wp', 'wpsubdomain'], 'wpsubdomain'),
    ]

    # Add PHP version combinations dynamically (eliminates 150+ duplicate lines)
    for php_ver in PHPVersionManager.SUPPORTED_VERSIONS:
        combinations.extend([
            # PHP version + mysql + html = mysql
            ([php_ver, 'mysql', 'html'], 'mysql'),
            ([php_ver, 'mysql'], 'mysql'),

            # PHP version + WordPress = WordPress
            (['wp', php_ver], 'wp'),
            (['wpsubdir', php_ver], 'wpsubdir'),
            (['wpsubdomain', php_ver], 'wpsubdomain'),
        ])

    # Find matching combination
    typelist_set = set(typelist)
    for combination, result_type in combinations:
        if typelist_set.issubset(set(combination)):
            return (result_type, cachetype)

    # No valid combination found
    raise RuntimeError("could not determine site and cache type")


def generate_random(length=24, charset=None):
    """
    Unified random string generator - replaces 3 separate functions with single configurable one.

    Args:
        length (int): Length of random string to generate (default: 24)
        charset (str): Character set to use (default: alphanumeric)

    Returns:
        str: Random string of specified length

    Examples:
        generate_random(24)  # Password (replaces generate_random_pass)
        generate_random(4)   # Short random (replaces generate_random)
        generate_random(8)   # Medium random (replaces generate_8_random)
    """
    if charset is None:
        charset = string.ascii_uppercase + string.ascii_lowercase + string.digits

    # Ensure we don't try to sample more characters than available
    actual_length = min(length, len(charset))
    return ''.join(random.sample(charset, actual_length))


# Backward compatibility wrappers (can be removed after updating all references)
def generate_random_pass():
    """Legacy wrapper - use generate_random(24) instead"""
    return generate_random(24)


def generate_8_random():
    """Legacy wrapper - use generate_random(8) instead"""
    return generate_random(8)


def deleteDB(self, dbname, dbuser, dbhost, exit=True):
    try:
        # Check if Database exists
        try:
            if WOMysql.check_db_exists(self, dbname):
                # Drop database if exists
                Log.debug(self, "dropping database `{0}`".format(dbname))
                WOMysql.execute(self,
                                "drop database `{0}`".format(dbname),
                                errormsg='Unable to drop database {0}'
                                .format(dbname))
        except StatementExcecutionError as e:
            Log.debug(self, str(e))
            Log.debug(self, "drop database failed")
            Log.info(self, "Database {0} not dropped".format(dbname))

        except MySQLConnectionError as e:
            Log.debug(self, str(e))
            Log.debug(self, "Mysql Connection problem occured")

        if dbuser != 'root':
            Log.debug(self, "dropping user `{0}`".format(dbuser))
            try:
                WOMysql.execute(self,
                                "drop user `{0}`@`{1}`"
                                .format(dbuser, dbhost))
            except StatementExcecutionError as e:
                Log.debug(self, str(e))
                Log.debug(self, "drop database user failed")
                Log.info(self, "Database {0} not dropped".format(dbuser))
            try:
                WOMysql.execute(self, "flush privileges")
            except StatementExcecutionError as e:
                Log.debug(self, str(e))
                Log.debug(self, "drop database failed")
                Log.info(self, "Database {0} not dropped".format(dbname))
    except Exception as e:
        Log.debug(self, str(e))
        Log.error(self, "Error occured while deleting database", exit)


def deleteWebRoot(self, webroot):
    # do some preprocessing before proceeding
    webroot = webroot.strip()
    if (webroot == "/var/www/" or webroot == "/var/www" or
            webroot == "/var/www/.." or webroot == "/var/www/."):
        Log.debug(self, "Tried to remove {0}, but didn't remove it"
                  .format(webroot))
        return False

    if os.path.isdir(webroot):
        Log.debug(self, "Removing {0}".format(webroot))
        WOFileUtils.rm(self, webroot)
        return True
    Log.debug(self, "{0} does not exist".format(webroot))
    return False


def removeNginxConf(self, domain):
    if os.path.isfile('/etc/nginx/sites-available/{0}'
                      .format(domain)):
        Log.debug(self, "Removing Nginx configuration")
        WOFileUtils.rm(self, '/etc/nginx/sites-enabled/{0}'
                       .format(domain))
        WOFileUtils.rm(self, '/etc/nginx/sites-available/{0}'
                       .format(domain))
        WOService.reload_service(self, 'nginx')
        WOGit.add(self, ["/etc/nginx"],
                  msg="Deleted {0} "
                  .format(domain))


def doCleanupAction(self, domain='', webroot='', dbname='', dbuser='',
                    dbhost=''):
    """
       Removes the nginx configuration and database for the domain provided.
       doCleanupAction(self, domain='sitename', webroot='',
                       dbname='', dbuser='', dbhost='')
    """
    if domain:
        if os.path.isfile('/etc/nginx/sites-available/{0}'
                          .format(domain)):
            removeNginxConf(self, domain)
            WOAcme.removeconf(self, domain)

    if webroot:
        deleteWebRoot(self, webroot)

    if dbname:
        if not dbuser:
            raise SiteError("dbuser not provided")
        if not dbhost:
            raise SiteError("dbhost not provided")
        deleteDB(self, dbname, dbuser, dbhost)

# setup letsencrypt for domain + www.domain

# copy wildcard certificate to a subdomain


def copyWildcardCert(self, wo_domain_name, wo_root_domain):

    if os.path.isfile("/var/www/{0}/conf/nginx/ssl.conf"
                      .format(wo_root_domain)):
        try:
            if not os.path.isdir("/etc/letsencrypt/shared"):
                WOFileUtils.mkdir(self, "/etc/letsencrypt/shared")
            if not os.path.isfile("/etc/letsencrypt/shared/{0}.conf"
                                  .format(wo_root_domain)):
                WOFileUtils.copyfile(self, "/var/www/{0}/conf/nginx/ssl.conf"
                                     .format(wo_root_domain),
                                     "/etc/letsencrypt/shared/{0}.conf"
                                     .format(wo_root_domain))
            WOFileUtils.create_symlink(self, ["/etc/letsencrypt/shared/"
                                              "{0}.conf"
                                              .format(wo_root_domain),
                                              '/var/www/{0}/conf/nginx/'
                                              'ssl.conf'
                                              .format(wo_domain_name)])
        except IOError as e:
            Log.debug(self, str(e))
            Log.debug(self, "Error occured while "
                      "creating symlink for ssl cert")

# letsencrypt cert renewal


def renewLetsEncrypt(self, wo_domain_name):

    ssl = WOShellExec.cmd_exec(
        self, "/etc/letsencrypt/acme.sh "
              "--config-home "
              "'/etc/letsencrypt/config' "
              "--renew -d {0} --ecc --force"
        .format(wo_domain_name))

    # mail_list = ''
    if not ssl:
        Log.error(self, "ERROR : Let's Encrypt certificate renewal FAILED!",
                  False)
        if (SSL.getexpirationdays(self, wo_domain_name) > 0):
            Log.error(self, "Your current certificate will expire within " +
                      str(SSL.getexpirationdays(self, wo_domain_name)) +
                      " days.", False)
        else:
            Log.error(self, "Your current certificate already expired!", False)

        # WOSendMail("wordops@{0}".format(wo_domain_name), wo_wp_email,
        #  "[FAIL] HTTPS cert renewal {0}".format(wo_domain_name),
        #          "Hi,\n\nHTTPS certificate renewal for https://{0}
        # was unsuccessful.".format(wo_domain_name) +
        #           "\nPlease check the WordOps log for reason
        # The current expiry date is : " +
        #           str(SSL.getExpirationDate(self, wo_domain_name)) +
        #           "\n\nFor support visit https://wordops.net/support .
        # \n\nBest regards,\nYour WordOps Worker", files=mail_list,
        #           port=25, isTls=False)
        Log.error(self, "Check the WO log for more details "
                  "`tail /var/log/wo/wordops.log`")

    WOGit.add(self, ["/etc/letsencrypt"],
              msg="Adding letsencrypt folder")
    # WOSendMail("wordops@{0}".format(wo_domain_name), wo_wp_email,
    # "[SUCCESS] Let's Encrypt certificate renewal {0}".format(wo_domain_name),
    #           "Hi,\n\nYour Let's Encrypt certificate has been renewed for
    # https://{0} .".format(wo_domain_name) +
    #           "\nYour new certificate will expire on : " +
    #          str(SSL.getExpirationDate(self, wo_domain_name)) +
    #           "\n\nBest regards,\nYour WordOps Worker", files=mail_list,
    #           port=25, isTls=False)

# redirect= False to disable https redirection


def setuprocketchat(self):
    if ((not WOVar.wo_platform_codename == 'bionic') and
            (not WOVar.wo_platform_codename == 'xenial')):
        Log.info(self, "Rocket.chat is only available on Ubuntu 16.04 "
                 "& 18.04 LTS")
        return False
    else:
        if not WOAptGet.is_installed(self, 'snapd'):
            WOAptGet.install(self, ["snapd"])
        if WOShellExec.cmd_exec(self, "snap install rocketchat-server"):
            return True
        return False


def setupngxblocker(self, domain, block=True):
    if block:
        if os.path.isdir('/var/www/{0}/conf/nginx'.format(domain)):
            if not os.path.isfile(
                '/var/www/{0}/conf/nginx/ngxblocker.conf.disabled'
                    .format(domain)):
                ngxconf = open(
                    "/var/www/{0}/conf/nginx/ngxblocker.conf"
                    .format(domain),
                    encoding='utf-8', mode='w')
                ngxconf.write(
                    "# Bad Bot Blocker\n"
                    "include /etc/nginx/bots.d/ddos.conf;\n"
                    "include /etc/nginx/bots.d/blockbots.conf;\n")
                ngxconf.close()
            else:
                WOFileUtils.mvfile(
                    self, '/var/www/{0}/conf/nginx/ngxblocker.conf.disabled'
                    .format(domain), '/var/www/{0}/conf/nginx/ngxblocker.conf'
                    .format(domain))
    else:
        if os.path.isfile('/var/www/{0}/conf/nginx/ngxblocker.conf'
                          .format(domain)):
            WOFileUtils.mvfile(
                self, '/var/www/{0}/conf/nginx/ngxblocker.conf'
                .format(domain),
                '/var/www/{0}/conf/nginx/ngxblocker.conf.disabled'
                .format(domain))
    return 0


def setup_letsencrypt(self, domain, webroot, acme_data=None):
    """
    Setup Let's Encrypt SSL certificate for a domain
    Consolidated from site_clone.py and site_restore.py

    Args:
        domain: Domain name
        webroot: Site webroot path
        acme_data: Optional custom acme configuration
    """
    (domain_type, _) = WODomain.getlevel(self, domain)
    parts = domain.split('.')

    # Determine domains to include in certificate
    if domain_type == 'subdomain' or (domain_type == '' and len(parts) > 2):
        acme_domains = [domain]
    else:
        acme_domains = [domain, f"www.{domain}"]

    # Set up acme data with defaults
    if acme_data is None:
        acme_data = dict(dns=False, acme_dns='dns_cf',
                        dnsalias=False, acme_alias='', keylength='')
        if self.app.config.has_section('letsencrypt'):
            acme_data['keylength'] = self.app.config.get('letsencrypt', 'keylength')
        else:
            acme_data['keylength'] = 'ec-384'

    # Setup and deploy certificate
    if WOAcme.setupletsencrypt(self, acme_domains, acme_data):
        WOAcme.deploycert(self, domain)
        SSL.httpsredirect(self, domain, acme_domains, True)
        SSL.siteurlhttps(self, domain)

        # Reload nginx
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, 'service nginx reload failed. '
                      'check issues with `nginx -t` command')
            return False

        # Add to git
        WOGit.add(self, [f"{webroot}/conf/nginx"],
                  msg=f"Adding letsencrypts config of site: {domain}")

        # Update site info
        updateSiteInfo(self, domain, ssl=True)

        Log.info(self, f"Congratulations! Successfully Configured SSL on "
                 f"https://{domain}")
        return True

    return False


def setup_letsencrypt_advanced(self, domain, pargs, domain_type, root_domain, webroot):
    """
    Advanced Let's Encrypt setup with full feature support
    Extracted from site_create.py to reduce complexity

    Args:
        domain: Domain name
        pargs: Parsed arguments from cement
        domain_type: Type of domain (subdomain, etc.)
        root_domain: Root domain
        webroot: Site webroot path
    """
    acme_domains = []
    letsencrypt = True
    Log.debug(self, "Going to issue Let's Encrypt certificate")

    # Setup acme data
    acmedata = dict(
        acme_domains, dns=False, acme_dns='dns_cf',
        dnsalias=False, acme_alias='', keylength='')

    if self.app.config.has_section('letsencrypt'):
        acmedata['keylength'] = self.app.config.get('letsencrypt', 'keylength')
    else:
        acmedata['keylength'] = 'ec-384'

    # Configure DNS validation
    if pargs.dns:
        Log.debug(self, "DNS validation enabled")
        acmedata['dns'] = True
        if not pargs.dns == 'dns_cf':
            Log.debug(self, f"DNS API : {pargs.dns}")
            acmedata['acme_dns'] = pargs.dns

    # Configure DNS alias
    if pargs.dnsalias:
        Log.debug(self, "DNS Alias enabled")
        acmedata['dnsalias'] = True
        acmedata['acme_alias'] = pargs.dnsalias

    # Determine certificate type
    if pargs.letsencrypt == "subdomain":
        Log.warn(self, 'Flag --letsencrypt=subdomain is '
                 'deprecated and not required anymore.')
        acme_subdomain = True
        acme_wildcard = False
    elif pargs.letsencrypt == "wildcard":
        acme_wildcard = True
        acme_subdomain = False
        acmedata['dns'] = True
    else:
        if domain_type == 'subdomain':
            Log.debug(self, f"Domain type = {domain_type}")
            acme_subdomain = True
        else:
            acme_subdomain = False
            acme_wildcard = False

    # Build domain list for certificate
    if acme_subdomain is True:
        Log.info(self, "Certificate type : subdomain")
        acme_domains = acme_domains + [f'{domain}']
    elif acme_wildcard is True:
        Log.info(self, "Certificate type : wildcard")
        acme_domains = acme_domains + [f'{domain}', f'*.{domain}']
    else:
        Log.info(self, "Certificate type : domain")
        acme_domains = acme_domains + [f'{domain}', f'www.{domain}']

    # Check for existing certificates and handle accordingly
    if WOAcme.cert_check(self, domain):
        SSL.archivedcertificatehandle(self, domain, acme_domains)
    else:
        if acme_subdomain is True:
            # Check if a wildcard cert for the root domain exists
            Log.debug(self, f"checkWildcardExist on *.{root_domain}")
            if SSL.checkwildcardexist(self, root_domain):
                Log.info(self, f"Using existing Wildcard SSL "
                         f"certificate from {root_domain} to secure {domain}")
                Log.debug(self, f"symlink wildcard "
                          f"cert between {domain} & {root_domain}")
                # Copy the cert from the root domain
                from wo.cli.plugins.site_functions import copyWildcardCert
                copyWildcardCert(self, domain, root_domain)
            else:
                # Check DNS records before issuing cert
                if not acmedata['dns'] is True:
                    if not pargs.force:
                        if not WOAcme.check_dns(self, acme_domains):
                            Log.error(self, "Aborting SSL certificate issuance")
                            return False
                Log.debug(self, f"Setup Cert with acme.sh for {domain}")
                if not WOAcme.setupletsencrypt(self, acme_domains, acmedata):
                    return False
                WOAcme.deploycert(self, domain)
        else:
            if not acmedata['dns'] is True:
                if not pargs.force:
                    if not WOAcme.check_dns(self, acme_domains):
                        Log.error(self, "Aborting SSL certificate issuance")
                        return False
            if not WOAcme.setupletsencrypt(self, acme_domains, acmedata):
                return False
            WOAcme.deploycert(self, domain)

        # Setup HSTS if requested
        if pargs.hsts:
            SSL.setuphsts(self, domain)

        # Configure HTTPS redirect and site URL
        SSL.httpsredirect(self, domain, acme_domains, True)
        SSL.siteurlhttps(self, domain)

        # Reload nginx
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, "service nginx reload failed. "
                      "check issues with `nginx -t` command")
            return False

        Log.info(self, f"Congratulations! Successfully Configured "
                 f"SSL on https://{domain}")

        # Add nginx conf folder into GIT
        WOGit.add(self, [f"{webroot}/conf/nginx"],
                  msg=f"Adding letsencrypts config of site: {domain}")
        updateSiteInfo(self, domain, ssl=letsencrypt)

    return True


def determine_site_type(pargs):
    """
    Determine site type and cache type based on arguments
    Extracted from site_create.py to reduce complexity

    Returns:
        tuple: (site_type, cache_type, additional_info)
    """
    try:
        stype, cache = detSitePar(vars(pargs))
    except RuntimeError as e:
        raise SiteError("Please provide valid options to creating site")

    # Handle proxy sites
    if stype is None and pargs.proxy:
        stype, cache = 'proxy', ''
        proxyinfo = pargs.proxy[0].strip()
        if not proxyinfo:
            raise SiteError("Please provide proxy server host information")
        proxyinfo = proxyinfo.split(':')
        host = proxyinfo[0].strip()
        port = '80' if len(proxyinfo) < 2 else proxyinfo[1].strip()
        return stype, cache, {'host': host, 'port': port}

    # Handle alias sites
    elif stype is None and pargs.alias:
        stype, cache = 'alias', ''
        alias_name = pargs.alias.strip()
        if not alias_name:
            raise SiteError("Please provide alias name")
        return stype, cache, {'alias_name': alias_name}

    # Handle subsites
    elif stype is None and pargs.subsiteof:
        stype, cache = 'subsite', ''
        subsiteof_name = pargs.subsiteof.strip()
        if not subsiteof_name:
            raise SiteError("Please provide multisite parent name")
        return stype, cache, {'subsiteof_name': subsiteof_name}

    # Default to html if nothing specified
    elif stype is None and not pargs.proxy and not pargs.alias and not pargs.subsiteof:
        stype, cache = 'html', 'basic'
        return stype, cache, {}

    # Validate no conflicts
    elif stype and pargs.proxy:
        raise SiteError("proxy should not be used with other site types")
    elif stype and pargs.alias:
        raise SiteError("alias should not be used with other site types")
    elif stype and pargs.subsiteof:
        raise SiteError("subsiteof should not be used with other site types")

    return stype, cache, {}


def create_database_backup(controller, site_info, target_dir, site_name):
    """Create a database backup for a site.

    Args:
        controller: The controller instance
        site_info: Site information object
        target_dir: Directory to store the backup
        site_name: Name of the site

    Returns:
        bool: True if backup was successful, False otherwise
    """
    if not site_info.db_name:
        Log.debug(controller, f"No database found for site {site_name}")
        return True

    dump_file = os.path.join(target_dir, f'{site_name}.sql')
    try:
        cmd = f"mysqldump --single-transaction --hex-blob {site_info.db_name} > {dump_file}"
        if not WOShellExec.cmd_exec(controller, cmd):
            Log.warn(controller, 'Database backup failed - mysqldump command failed')
            return False
        Log.debug(controller, f"Database backup created: {dump_file}")
        return True
    except CommandExecutionError as e:
        Log.debug(controller, f"Database backup error: {str(e)}")
        Log.warn(controller, 'Database backup failed - command execution error')
        return False


def collect_site_metadata(controller, site_info, site_name):
    """Collect site metadata including HTTP auth credentials.

    Args:
        controller: The controller instance
        site_info: Site information object
        site_name: Name of the site

    Returns:
        dict: Site metadata
    """
    metadata = {
        'id': site_info.id,
        'sitename': site_info.sitename,
        'site_type': site_info.site_type,
        'cache_type': site_info.cache_type,
        'site_path': site_info.site_path,
        'created_on': site_info.created_on.isoformat() if site_info.created_on else None,
        'is_enabled': site_info.is_enabled,
        'is_ssl': site_info.is_ssl,
        'storage_fs': site_info.storage_fs,
        'storage_db': site_info.storage_db,
        'db_name': site_info.db_name,
        'db_user': site_info.db_user,
        'db_password': site_info.db_password,
        'db_host': site_info.db_host,
        'is_hhvm': site_info.is_hhvm,
        'php_version': site_info.php_version,
    }

    # Read HTTP auth credentials if they exist
    slug = site_name.replace('.', '-').lower()
    cred_file = f'/etc/nginx/acl/{slug}/credentials'
    if os.path.isfile(cred_file):
        try:
            with open(cred_file, 'r') as cf:
                cred_line = cf.readline().strip()
            if ':' in cred_line:
                user, passwd = cred_line.split(':', 1)
                metadata['httpauth_user'] = user
                metadata['httpauth_pass'] = passwd
        except OSError as e:
            Log.debug(controller, f"Could not read credentials file: {str(e)}")

    return metadata


def create_site_archive(controller, domain_dir, timestamp):
    """Create a compressed archive from the backup directory.

    Args:
        controller: The controller instance
        domain_dir: Base directory for the domain
        timestamp: Timestamp string for the backup

    Returns:
        bool: True if archive was created successfully, False otherwise
    """
    target_dir = os.path.join(domain_dir, timestamp)
    archive = os.path.join(domain_dir, f'{timestamp}.tar.zst')

    try:
        if WOShellExec.cmd_exec(controller, f"tar --zstd -cf {archive} -C {domain_dir} {timestamp}"):
            WOFileUtils.remove(controller, [target_dir])
            Log.debug(controller, f"Archive created: {archive}")
            return True
        else:
            Log.warn(controller, 'Failed to create backup archive')
            return False
    except CommandExecutionError as e:
        Log.debug(controller, f"Archive creation error: {str(e)}")
        Log.warn(controller, 'Failed to create backup archive')
        return False


def handle_site_error_cleanup(self, domain, webroot, db_name=None, db_user=None, db_host=None):
    """
    Standardized error cleanup for site creation failures
    Extracted from repetitive cleanup code in site_create.py
    """
    Log.info(self, Log.FAIL + "There was a serious error encountered...")
    Log.info(self, Log.FAIL + "Cleaning up afterwards...")

    # Clean up webroot
    doCleanupAction(self, domain=domain, webroot=webroot)

    # Clean up database if provided
    if db_name and db_user and db_host:
        doCleanupAction(self, domain=domain,
                       dbname=db_name,
                       dbuser=db_user,
                       dbhost=db_host)

    # Remove site info
    deleteSiteInfo(self, domain)

    Log.error(self, "Check the log for details: "
              "`tail /var/log/wo/wordops.log` and please try again")


