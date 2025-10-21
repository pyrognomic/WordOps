"""Stack Plugin for WordOps - Refactored Version

This module manages stack operations (install, remove, purge) for WordOps.
It has been refactored to improve maintainability, reduce code duplication,
and add type hints.
"""

import os
from typing import List, Tuple, Dict, Optional, Any

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.stack_migrate import WOStackMigrateController
from wo.cli.plugins.stack_pref import post_pref, pre_pref, pre_stack
from wo.cli.plugins.stack_services import WOStackStatusController
from wo.cli.plugins.stack_upgrade import WOStackUpgradeController
from wo.core.aptget import WOAptGet
from wo.core.download import WODownload
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.mysql import WOMysql
from wo.core.services import WOService
from wo.core.shellexec import WOShellExec
from wo.core.variables import WOVar
from wo.core.nginx import check_config
from wo.core.git import WOGit


def wo_stack_hook(app: Any) -> None:
    """Hook function for stack operations."""
    pass


class PackageManager:
    """Helper class to manage package lists and validation."""

    def __init__(self, controller: 'WOStackController'):
        self.controller = controller
        self.apt_packages: List[str] = []
        self.packages: List[List[str]] = []

    def add_apt_package(self, package: str) -> None:
        """Add an APT package to the install list."""
        if package not in self.apt_packages:
            self.apt_packages.append(package)

    def add_apt_packages(self, packages: List[str]) -> None:
        """Add multiple APT packages to the install list."""
        for package in packages:
            self.add_apt_package(package)

    def add_download_package(self, package: List[str]) -> None:
        """Add a download package to the install list.

        Args:
            package: [url, destination_path, description]
        """
        if package not in self.packages:
            self.packages.append(package)

    def add_download_packages(self, packages: List[List[str]]) -> None:
        """Add multiple download packages to the install list."""
        for package in packages:
            self.add_download_package(package)


class StackComponentInstaller:
    """Handles installation of individual stack components."""

    def __init__(self, controller: 'WOStackController', pkg_manager: PackageManager):
        self.controller = controller
        self.pkg_manager = pkg_manager

    def install_nginx(self) -> None:
        """Install Nginx if not already installed."""
        if not WOAptGet.is_exec(self.controller, 'nginx'):
            Log.debug(self.controller, "Setting apt_packages variable for Nginx")
            self.pkg_manager.add_apt_packages(WOVar.wo_nginx)
        else:
            Log.debug(self.controller, "Nginx already installed")

    def install_redis(self) -> None:
        """Install Redis if not already installed."""
        if not WOAptGet.is_installed(self.controller, 'redis-server'):
            self.pkg_manager.add_apt_packages(WOVar.wo_redis)
        else:
            Log.debug(self.controller, "Redis already installed")

    def install_php_version(self, version_key: str, version_number: str) -> None:
        """Install a specific PHP version.

        Args:
            version_key: e.g., 'php74', 'php80'
            version_number: e.g., '7.4', '8.0'
        """
        Log.debug(self.controller, f"Setting apt_packages variable for PHP {version_number}")
        if not WOAptGet.is_installed(self.controller, f'php{version_number}-fpm'):
            wo_vars = {
                'php74': WOVar.wo_php74,
                'php80': WOVar.wo_php80,
                'php81': WOVar.wo_php81,
                'php82': WOVar.wo_php82,
                'php83': WOVar.wo_php83,
                'php84': WOVar.wo_php84,
            }
            self.pkg_manager.add_apt_packages(wo_vars[version_key])
            self.pkg_manager.add_apt_packages(WOVar.wo_php_extra)
        else:
            Log.debug(self.controller, f"PHP {version_number} already installed")
            Log.info(self.controller, f"PHP {version_number} already installed")

    def install_mysql(self) -> None:
        """Install MySQL/MariaDB if not already installed."""
        Log.debug(self.controller, "Setting apt_packages variable for MySQL")
        if not WOMysql.mariadb_ping(self.controller):
            self.pkg_manager.add_apt_packages(WOVar.wo_mysql)
        else:
            Log.debug(self.controller, "MySQL already installed and alive")
            Log.info(self.controller, "MySQL already installed and alive")

    def install_mysql_client(self) -> None:
        """Install MySQL client for remote MySQL server."""
        Log.debug(self.controller, "Setting apt_packages variable for MySQL Client")
        if not WOMysql.mariadb_ping(self.controller):
            self.pkg_manager.add_apt_packages(WOVar.wo_mysql_client)
        else:
            Log.debug(self.controller, "MySQL already installed and alive")
            Log.info(self.controller, "MySQL already installed and alive")

    def install_wpcli(self) -> None:
        """Install WP-CLI if not already installed."""
        if not WOAptGet.is_exec(self.controller, 'wp'):
            Log.debug(self.controller, "Setting packages variable for WP-CLI")
            self.pkg_manager.add_download_package([
                WOVar.wpcli_url,
                "/usr/local/bin/wp",
                "WP-CLI"
            ])
        else:
            Log.debug(self.controller, "WP-CLI is already installed")
            Log.info(self.controller, "WP-CLI is already installed")

    def install_fail2ban(self) -> None:
        """Install Fail2ban if not already installed."""
        if not WOAptGet.is_installed(self.controller, 'fail2ban'):
            Log.debug(self.controller, "Setting apt_packages variable for Fail2ban")
            self.pkg_manager.add_apt_packages(WOVar.wo_fail2ban)
        else:
            Log.debug(self.controller, "Fail2ban already installed")
            Log.info(self.controller, "Fail2ban already installed")

    def install_clamav(self) -> None:
        """Install ClamAV if not already installed."""
        if not WOAptGet.is_installed(self.controller, 'clamav'):
            Log.debug(self.controller, "Setting apt_packages variable for ClamAV")
            self.pkg_manager.add_apt_packages(WOVar.wo_clamav)
        else:
            Log.debug(self.controller, "ClamAV already installed")
            Log.info(self.controller, "ClamAV already installed")

    def install_ufw(self) -> None:
        """Install UFW firewall."""
        Log.debug(self.controller, "Setting apt_packages variable for UFW")
        self.pkg_manager.add_apt_package("ufw")

    def install_sendmail(self) -> None:
        """Install Sendmail if not already installed."""
        Log.debug(self.controller, "Setting apt_packages variable for Sendmail")
        if (not WOAptGet.is_installed(self.controller, 'sendmail') and
                not WOAptGet.is_installed(self.controller, 'postfix')):
            self.pkg_manager.add_apt_package("sendmail")
        else:
            if WOAptGet.is_installed(self.controller, 'sendmail'):
                Log.debug(self.controller, "Sendmail already installed")
                Log.info(self.controller, "Sendmail already installed")
            else:
                Log.debug(self.controller, "Another mta (Postfix) is already installed")
                Log.info(self.controller, "Another mta (Postfix) is already installed")

    def install_proftpd(self) -> None:
        """Install ProFTPd if not already installed."""
        if not WOAptGet.is_installed(self.controller, 'proftpd-basic'):
            Log.debug(self.controller, "Setting apt_packages variable for ProFTPd")
            self.pkg_manager.add_apt_package("proftpd-basic")
        else:
            Log.debug(self.controller, "ProFTPd already installed")
            Log.info(self.controller, "ProFTPd already installed")

    def install_phpmyadmin(self) -> None:
        """Install phpMyAdmin if not already installed."""
        if not os.path.isdir(f'{WOVar.wo_webroot}22222/htdocs/db/pma'):
            Log.debug(self.controller, "Setting packages variable for phpMyAdmin")
            self.pkg_manager.add_download_package([
                "https://www.phpmyadmin.net/downloads/phpMyAdmin-latest-all-languages.tar.gz",
                "/var/lib/wo/tmp/pma.tar.gz",
                "PHPMyAdmin"
            ])
        else:
            Log.debug(self.controller, "phpMyAdmin already installed")
            Log.info(self.controller, "phpMyAdmin already installed")

    def install_phpredisadmin(self) -> None:
        """Install phpRedisAdmin if not already installed."""
        if not os.path.isdir(f'{WOVar.wo_webroot}22222/htdocs/cache/redis/phpRedisAdmin'):
            Log.debug(self.controller, "Setting packages variable for phpRedisAdmin")
            self.pkg_manager.add_download_package([
                "https://github.com/erikdubbelboer/phpRedisAdmin/archive/v1.11.3.tar.gz",
                "/var/lib/wo/tmp/pra.tar.gz",
                "phpRedisAdmin"
            ])
        else:
            Log.debug(self.controller, "phpRedisAdmin already installed")
            Log.info(self.controller, "phpRedisAdmin already installed")

    def install_composer(self) -> None:
        """Install Composer if not already installed."""
        if not WOAptGet.is_exec(self.controller, 'composer'):
            Log.debug(self.controller, "Setting packages variable for Composer")
            self.pkg_manager.add_download_package([
                "https://getcomposer.org/installer",
                "/var/lib/wo/tmp/composer-install",
                "Composer"
            ])
        else:
            Log.debug(self.controller, "Composer already installed")
            Log.info(self.controller, "Composer already installed")

    def install_adminer(self) -> None:
        """Install Adminer if not already installed."""
        adminer_path = f"{WOVar.wo_webroot}22222/htdocs/db/adminer/index.php"
        if not os.path.isfile(adminer_path):
            Log.debug(self.controller, "Setting packages variable for Adminer")
            self.pkg_manager.add_download_packages([
                [
                    "https://www.adminer.org/latest.php",
                    f"{WOVar.wo_webroot}22222/htdocs/db/adminer/index.php",
                    "Adminer"
                ],
                [
                    "https://raw.githubusercontent.com/vrana/adminer/master/designs/pepa-linha/adminer.css",
                    f"{WOVar.wo_webroot}22222/htdocs/db/adminer/adminer.css",
                    "Adminer theme"
                ]
            ])
        else:
            Log.debug(self.controller, "Adminer already installed")
            Log.info(self.controller, "Adminer already installed")

    def install_mysqltuner(self) -> None:
        """Install MySQLTuner if not already installed."""
        if not os.path.isfile("/usr/bin/mysqltuner"):
            Log.debug(self.controller, "Setting packages variable for MySQLTuner")
            self.pkg_manager.add_download_package([
                "https://raw.githubusercontent.com/major/MySQLTuner-perl/master/mysqltuner.pl",
                "/usr/bin/mysqltuner",
                "MySQLTuner"
            ])
        else:
            Log.debug(self.controller, "MySQLtuner already installed")
            Log.info(self.controller, "MySQLtuner already installed")

    def install_netdata(self) -> None:
        """Install Netdata monitoring suite if not already installed."""
        if not os.path.isdir('/opt/netdata') and not os.path.isdir("/etc/netdata"):
            Log.debug(self.controller, "Setting packages variable for Netdata")
            self.pkg_manager.add_download_package([
                WOVar.netdata_script_url,
                '/var/lib/wo/tmp/kickstart.sh',
                'Netdata'
            ])
        else:
            Log.debug(self.controller, "Netdata already installed")
            Log.info(self.controller, "Netdata already installed")

    def install_dashboard(self) -> None:
        """Install WordOps Dashboard if not already installed."""
        if not os.path.isfile(f'{WOVar.wo_webroot}22222/htdocs/index.php'):
            Log.debug(self.controller, "Setting packages variable for WO-Dashboard")
            self.pkg_manager.add_download_package([
                f"https://github.com/WordOps/wordops-dashboard/releases/download/v{WOVar.wo_dashboard}/wordops-dashboard.tar.gz",
                "/var/lib/wo/tmp/wo-dashboard.tar.gz",
                "WordOps Dashboard"
            ])
        else:
            Log.debug(self.controller, "WordOps dashboard already installed")
            Log.info(self.controller, "WordOps dashboard already installed")

    def install_extplorer(self) -> None:
        """Install eXtplorer file manager if not already installed."""
        if not os.path.isdir(f'{WOVar.wo_webroot}22222/htdocs/files'):
            Log.debug(self.controller, "Setting packages variable for eXtplorer")
            self.pkg_manager.add_download_package([
                f"https://github.com/soerennb/extplorer/archive/v{WOVar.wo_extplorer}.tar.gz",
                "/var/lib/wo/tmp/extplorer.tar.gz",
                "eXtplorer"
            ])
        else:
            Log.debug(self.controller, "eXtplorer is already installed")
            Log.info(self.controller, "eXtplorer is already installed")

    def install_ngxblocker(self) -> None:
        """Install Nginx Ultimate Bad Bot Blocker if not already installed."""
        if not os.path.isdir('/etc/nginx/bots.d'):
            Log.debug(self.controller, "Setting packages variable for ngxblocker")
            self.pkg_manager.add_download_package([
                "https://raw.githubusercontent.com/mitchellkrogza/nginx-ultimate-bad-bot-blocker/master/install-ngxblocker",
                "/usr/local/sbin/install-ngxblocker",
                "ngxblocker"
            ])
        else:
            Log.debug(self.controller, "ngxblocker is already installed")
            Log.info(self.controller, "ngxblocker is already installed")

    def install_cheat(self) -> None:
        """Install cheat.sh if not already installed."""
        if not os.path.exists('/usr/local/bin/cht.sh') and not os.path.exists('/usr/bin/cht.sh'):
            Log.debug(self.controller, 'Setting packages variable for cheat.sh')
            self.pkg_manager.add_download_packages([
                [
                    "https://raw.githubusercontent.com/chubin/cheat.sh/master/share/cht.sh.txt",
                    "/usr/local/bin/cht.sh",
                    "cheat.sh"
                ],
                [
                    "https://raw.githubusercontent.com/chubin/cheat.sh/master/share/bash_completion.txt",
                    "/etc/bash_completion.d/cht.sh",
                    "bash_completion"
                ]
            ])

    def install_nanorc(self) -> None:
        """Install nanorc syntax highlighting if not already installed."""
        if not os.path.exists('/usr/share/nano-syntax-highlighting'):
            Log.debug(self.controller, "Setting packages variable for nanorc")
            self.pkg_manager.add_apt_package('nano')

    def install_utils(self) -> None:
        """Install various utility packages."""
        Log.debug(self.controller, "Setting packages variable for utils")
        self.pkg_manager.add_download_packages([
            [
                "https://raw.githubusercontent.com/rtCamp/eeadmin/master/cache/nginx/clean.php",
                f"{WOVar.wo_webroot}22222/htdocs/cache/nginx/clean.php",
                "clean.php"
            ],
            [
                "https://raw.github.com/rlerdorf/opcache-status/master/opcache.php",
                f"{WOVar.wo_webroot}22222/htdocs/cache/opcache/opcache.php",
                "opcache.php"
            ],
            [
                "https://raw.github.com/amnuts/opcache-gui/master/index.php",
                f"{WOVar.wo_webroot}22222/htdocs/cache/opcache/opgui.php",
                "Opgui"
            ],
            [
                "https://raw.githubusercontent.com/mlazarov/ocp/master/ocp.php",
                f"{WOVar.wo_webroot}22222/htdocs/cache/opcache/ocp.php",
                "OCP.php"
            ],
            [
                "https://github.com/jokkedk/webgrind/archive/master.tar.gz",
                '/var/lib/wo/tmp/webgrind.tar.gz',
                'Webgrind'
            ],
            [
                "https://www.percona.com/get/pt-query-digest",
                "/usr/bin/pt-query-advisor",
                "pt-query-advisor"
            ]
        ])


class BrotliManager:
    """Handles Brotli compression enable/disable operations."""

    @staticmethod
    def enable(controller: 'WOStackController') -> None:
        """Enable Brotli compression for Nginx."""
        Log.wait(controller, "Enabling Brotli")
        WOGit.add(controller, ["/etc/nginx"], msg="Commiting pending changes")

        if os.path.exists('/etc/nginx/conf.d/brotli.conf.disabled'):
            WOFileUtils.mvfile(controller,
                             '/etc/nginx/conf.d/brotli.conf.disabled',
                             '/etc/nginx/conf.d/brotli.conf')
        else:
            Log.failed(controller, "Enabling Brotli")
            Log.error(controller, "Brotli is already enabled")

        if os.path.exists('/etc/nginx/conf.d/gzip.conf'):
            WOFileUtils.mvfile(controller,
                             '/etc/nginx/conf.d/gzip.conf',
                             '/etc/nginx/conf.d/gzip.conf.disabled')

        if check_config(controller):
            Log.valide(controller, "Enabling Brotli")
            WOGit.add(controller, ["/etc/nginx"], msg="Enabling Brotli")
            WOService.reload_service(controller, "nginx")
        else:
            Log.failed(controller, "Enabling Brotli")
            WOGit.rollback(controller, ["/etc/nginx"])

    @staticmethod
    def disable(controller: 'WOStackController') -> None:
        """Disable Brotli compression for Nginx."""
        Log.wait(controller, "Disabling Brotli")
        WOGit.add(controller, ["/etc/nginx"], msg="Commiting pending changes")

        if os.path.exists('/etc/nginx/conf.d/brotli.conf'):
            WOFileUtils.mvfile(controller,
                             '/etc/nginx/conf.d/brotli.conf',
                             '/etc/nginx/conf.d/brotli.conf.disabled')
        else:
            Log.failed(controller, "Disabling Brotli")
            Log.error(controller, "Brotli is already disabled")

        if os.path.exists('/etc/nginx/conf.d/gzip.conf.disabled'):
            WOFileUtils.mvfile(controller,
                             '/etc/nginx/conf.d/gzip.conf.disabled',
                             '/etc/nginx/conf.d/gzip.conf')

        if check_config(controller):
            Log.valide(controller, "Disabling Brotli")
            WOGit.add(controller, ["/etc/nginx"], msg="Disabling Brotli")
            WOService.reload_service(controller, "nginx")
        else:
            Log.failed(controller, "Disabling Brotli")
            WOGit.rollback(controller, ["/etc/nginx"])


class StackRemover:
    """Handles removal and purging of stack components."""

    def __init__(self, controller: 'WOStackController', purge: bool = False):
        self.controller = controller
        self.purge = purge
        self.apt_packages: List[str] = []
        self.packages: List[str] = []

    def _get_packages_for_removal(self, pargs: Any) -> Tuple[List[str], List[str]]:
        """Determine which packages to remove based on arguments.

        Args:
            pargs: Parsed arguments from command line

        Returns:
            Tuple of (apt_packages, file_packages)
        """
        # Process argument flags
        if getattr(pargs, 'php', False):
            self._set_default_php_version(pargs)

        if getattr(pargs, 'mariadb', False):
            pargs.mysql = True

        # Handle --all flag
        if getattr(pargs, 'all', False):
            self._handle_all_flag(pargs)

        # Handle preset stacks
        if getattr(pargs, 'web', False):
            self._handle_web_stack(pargs)

        if getattr(pargs, 'admin', False):
            self._handle_admin_stack(pargs)

        if getattr(pargs, 'security', False):
            self._handle_security_stack(pargs)

        # Process individual components
        self._process_individual_components(pargs)

        return self.apt_packages, self.packages

    def _set_default_php_version(self, pargs: Any) -> None:
        """Set the default PHP version based on config."""
        if self.controller.app.config.has_section('php'):
            config_php_ver = self.controller.app.config.get('php', 'version')
            current_php = config_php_ver.replace(".", "")
            setattr(pargs, f'php{current_php}', True)

    def _handle_all_flag(self, pargs: Any) -> None:
        """Handle --all flag for removal."""
        pargs.web = True
        pargs.admin = True
        for version_key in WOVar.wo_php_versions.keys():
            setattr(pargs, version_key, True)
        pargs.fail2ban = True
        pargs.proftpd = True
        pargs.utils = True
        pargs.redis = True
        pargs.security = True
        pargs.nanorc = True
        self.packages.append(f'{WOVar.wo_webroot}22222/htdocs')

    def _handle_web_stack(self, pargs: Any) -> None:
        """Handle --web stack flag."""
        pargs.nginx = True
        pargs.php = True
        pargs.mysql = True
        pargs.wpcli = True
        pargs.sendmail = True

    def _handle_admin_stack(self, pargs: Any) -> None:
        """Handle --admin stack flag."""
        pargs.composer = True
        pargs.utils = True
        pargs.netdata = True
        pargs.mysqltuner = True
        pargs.cheat = True
        if self.purge:
            self.packages.append(f'{WOVar.wo_webroot}22222/htdocs')

    def _handle_security_stack(self, pargs: Any) -> None:
        """Handle --security stack flag."""
        pargs.fail2ban = True
        pargs.clamav = True
        pargs.ufw = True
        pargs.ngxblocker = True

    def _process_individual_components(self, pargs: Any) -> None:
        """Process individual component flags for removal."""
        # Nginx
        if getattr(pargs, 'nginx', False) and WOAptGet.is_installed(self.controller, 'nginx-custom'):
            Log.debug(self.controller, "Removing apt_packages variable of Nginx")
            self.apt_packages.extend(WOVar.wo_nginx)

        # PHP versions
        self._process_php_versions(pargs)

        # Redis
        if getattr(pargs, 'redis', False) and WOAptGet.is_installed(self.controller, 'redis-server'):
            Log.debug(self.controller, "Remove apt_packages variable of Redis")
            self.apt_packages.append("redis-server")

        # MySQL/MariaDB
        if getattr(pargs, 'mysql', False):
            self._process_mysql_removal(pargs)

        # MySQL Client
        if getattr(pargs, 'mysqlclient', False) and WOMysql.mariadb_ping(self.controller):
            Log.debug(self.controller, "Removing apt_packages variable for MySQL Client")
            self.apt_packages.extend(WOVar.wo_mysql_client)

        # Fail2ban
        if getattr(pargs, 'fail2ban', False) and WOAptGet.is_installed(self.controller, 'fail2ban'):
            Log.debug(self.controller, "Remove apt_packages variable of Fail2ban")
            self.apt_packages.extend(WOVar.wo_fail2ban)

        # ClamAV
        if getattr(pargs, 'clamav', False) and WOAptGet.is_installed(self.controller, 'clamav'):
            Log.debug(self.controller, "Setting apt_packages variable for ClamAV")
            self.apt_packages.extend(WOVar.wo_clamav)

        # Sendmail
        if getattr(pargs, 'sendmail', False) and WOAptGet.is_installed(self.controller, 'sendmail'):
            Log.debug(self.controller, "Setting apt_packages variable for Sendmail")
            self.apt_packages.append("sendmail")

        # ProFTPd
        if getattr(pargs, 'proftpd', False) and WOAptGet.is_installed(self.controller, 'proftpd-basic'):
            Log.debug(self.controller, "Remove apt_packages variable for ProFTPd")
            self.apt_packages.append("proftpd-basic")

        # UFW
        if getattr(pargs, 'ufw', False) and WOAptGet.is_installed(self.controller, 'ufw'):
            Log.debug(self.controller, "Remove apt_packages variable for UFW")
            WOShellExec.cmd_exec(self.controller, 'ufw disable && ufw --force reset')

        # Process file-based packages
        self._process_file_packages(pargs)

    def _process_php_versions(self, pargs: Any) -> None:
        """Process PHP version removal."""
        wo_vars = {
            'php74': WOVar.wo_php74,
            'php80': WOVar.wo_php80,
            'php81': WOVar.wo_php81,
            'php82': WOVar.wo_php82,
            'php83': WOVar.wo_php83,
            'php84': WOVar.wo_php84,
        }

        for parg_version, version in WOVar.wo_php_versions.items():
            if getattr(pargs, parg_version, False):
                Log.debug(self.controller, f"Setting apt_packages variable for PHP {version}")

                if WOAptGet.is_installed(self.controller, f'php{version}-fpm'):
                    self.apt_packages.extend(wo_vars[parg_version])

                    # Check if other versions are installed
                    other_versions_installed = any(
                        WOAptGet.is_installed(self.controller, f'php{other_version}-fpm')
                        for other_version in WOVar.wo_php_versions.values()
                        if other_version != version
                    )

                    if not other_versions_installed:
                        self.apt_packages.extend(WOVar.wo_php_extra)
                else:
                    Log.debug(self.controller, f"PHP {version} is not installed")
                    Log.info(self.controller, f"PHP {version} is not installed")

    def _process_mysql_removal(self, pargs: Any) -> None:
        """Process MySQL/MariaDB removal."""
        if WOAptGet.is_installed(self.controller, 'mariadb-server'):
            Log.debug(self.controller, "Removing apt_packages variable of MySQL")
            if self.purge:
                self.apt_packages.extend(['mariadb-server', 'mysql-common', 'mariadb-client'])
                self.packages.extend(['/etc/mysql', '/var/lib/mysql'])
            else:
                self.apt_packages.extend(WOVar.wo_mysql)
        elif not self.purge:
            Log.info(self.controller, "MariaDB is not installed")

    def _process_file_packages(self, pargs: Any) -> None:
        """Process file-based package removals."""
        # nanorc
        if getattr(pargs, 'nanorc', False) and os.path.exists('/usr/share/nano-syntax-highlighting'):
            Log.debug(self.controller, "Add nano to packages list")
            self.packages.append("/usr/share/nano-syntax-highlighting")

        # WP-CLI
        if getattr(pargs, 'wpcli', False):
            Log.debug(self.controller, "Removing package variable of WPCLI")
            for wp_path in ['/usr/local/bin/wp', '/usr/bin/wp']:
                if os.path.isfile(wp_path):
                    self.packages.append(wp_path)
            if WOAptGet.is_installed(self.controller, 'wp-cli'):
                self.apt_packages.append('wp-cli')

        # phpMyAdmin
        if getattr(pargs, 'phpmyadmin', False):
            pma_path = f'{WOVar.wo_webroot}22222/htdocs/db/pma'
            if os.path.isdir(pma_path):
                Log.debug(self.controller, "Removing package of phpMyAdmin")
                self.packages.append(pma_path)

        # Composer
        if getattr(pargs, 'composer', False) and os.path.isfile('/usr/local/bin/composer'):
            Log.debug(self.controller, "Removing package of Composer")
            self.packages.append('/usr/local/bin/composer')

        # MySQLTuner
        if getattr(pargs, 'mysqltuner', False) and os.path.isfile('/usr/bin/mysqltuner'):
            Log.debug(self.controller, "Removing packages for MySQLTuner")
            self.packages.append('/usr/bin/mysqltuner')

        # cheat.sh
        if getattr(pargs, 'cheat', False) and os.path.isfile('/usr/local/bin/cht.sh'):
            Log.debug(self.controller, "Removing packages for cheat.sh")
            self.packages.extend([
                '/usr/local/bin/cht.sh',
                '/usr/local/bin/cheat',
                '/etc/bash_completion.d/cht.sh'
            ])

        # phpRedisAdmin
        if getattr(pargs, 'phpredisadmin', False):
            redis_path = f'{WOVar.wo_webroot}22222/htdocs/cache/redis'
            if os.path.isdir(redis_path):
                Log.debug(self.controller, "Removing package variable of phpRedisAdmin")
                self.packages.append(redis_path)

        # Adminer
        if getattr(pargs, 'adminer', False):
            adminer_path = f'{WOVar.wo_webroot}22222/htdocs/db/adminer'
            if os.path.isdir(adminer_path):
                Log.debug(self.controller, "Removing package variable of Adminer")
                self.packages.append(adminer_path)

        # Utils
        if getattr(pargs, 'utils', False):
            Log.debug(self.controller, "Removing package variable of utils")
            self.packages.extend([
                f'{WOVar.wo_webroot}22222/htdocs/php/webgrind/',
                f'{WOVar.wo_webroot}22222/htdocs/cache/opcache',
                f'{WOVar.wo_webroot}22222/htdocs/cache/nginx/clean.php',
                '/usr/bin/pt-query-advisor',
                f'{WOVar.wo_webroot}22222/htdocs/db/anemometer'
            ])

        # Netdata
        if getattr(pargs, 'netdata', False) and (os.path.exists('/opt/netdata') or os.path.exists('/etc/netdata')):
            Log.debug(self.controller, "Removing Netdata")
            self.packages.append('/var/lib/wo/tmp/kickstart.sh')

        # WordOps Dashboard
        if getattr(pargs, 'dashboard', False):
            dashboard_index = f'{WOVar.wo_webroot}22222/htdocs/index.php'
            dashboard_html = f'{WOVar.wo_webroot}22222/htdocs/index.html'
            if os.path.isfile(dashboard_index) or os.path.isfile(dashboard_html):
                Log.debug(self.controller, "Removing Wo-Dashboard")
                self.packages.extend([
                    f'{WOVar.wo_webroot}22222/htdocs/assets',
                    dashboard_index,
                    dashboard_html
                ])

        # ngxblocker
        if getattr(pargs, 'ngxblocker', False) and os.path.isfile('/usr/local/sbin/setup-ngxblocker'):
            self.packages.extend([
                '/usr/local/sbin/setup-ngxblocker',
                '/usr/local/sbin/install-ngxblocker',
                '/usr/local/sbin/update-ngxblocker',
                '/etc/nginx/conf.d/globalblacklist.conf',
                '/etc/nginx/conf.d/botblocker-nginx-settings.conf',
                '/etc/nginx/bots.d'
            ])

    def execute_removal(self, pargs: Any) -> None:
        """Execute the removal/purge operation.

        Args:
            pargs: Parsed command-line arguments
        """
        apt_packages, packages = self._get_packages_for_removal(pargs)

        if not apt_packages and not packages:
            return

        # Confirm with user
        if not pargs.force:
            if self.purge:
                prompt = ('Are you sure you to want to purge stacks from this server?\n'
                         'Package configuration and data will not remain on this server '
                         'after this operation.\nPurge stacks [y/N]')
            else:
                prompt = ('Are you sure you to want to remove from server.\n'
                         'Package configuration will remain on server after this operation.\n'
                         'Remove stacks [y/N]?')

            user_input = input(prompt)
            if user_input not in ["Y", "y"]:
                Log.error(self.controller, f"Not starting stack {'purge' if self.purge else 'removal'}")

        # Stop services before removal
        self._stop_services(apt_packages)

        # Handle Netdata uninstaller
        if '/var/lib/wo/tmp/kickstart.sh' in packages:
            self._uninstall_netdata(packages)

        # Remove packages
        if packages:
            action = "Purging Packages" if self.purge else "Removing packages"
            Log.wait(self.controller, f"{action}            ")
            WOFileUtils.remove(self.controller, packages)
            Log.valide(self.controller, f"{action}            ")

            # Handle nanorc cleanup
            if '/usr/share/nano-syntax-highlighting' in packages:
                self._cleanup_nanorc()

        # Remove APT packages
        if apt_packages:
            action = "Purging APT Packages" if self.purge else "Removing APT packages"
            Log.debug(self.controller, f"{action}")
            Log.wait(self.controller, f"{action}       ")
            WOAptGet.remove(self.controller, apt_packages, purge=self.purge)
            WOAptGet.auto_remove(self.controller)
            Log.valide(self.controller, f"{action}       ")

        action = "purged" if self.purge else "removed"
        Log.info(self.controller, f"Successfully {action} packages")

    def _stop_services(self, apt_packages: List[str]) -> None:
        """Stop services before removal.

        Args:
            apt_packages: List of APT packages being removed
        """
        if 'nginx-custom' in apt_packages:
            WOService.stop_service(self.controller, 'nginx')

        if 'fail2ban' in apt_packages:
            WOService.stop_service(self.controller, 'fail2ban')

        if 'mariadb-server' in apt_packages:
            if self.purge and self.controller.app.config.has_section('mysql'):
                if self.controller.app.config.get('mysql', 'grant-host') == 'localhost':
                    WOMysql.backupAll(self.controller)
            else:
                WOMysql.backupAll(self.controller)
            WOService.stop_service(self.controller, 'mysql')

        # Stop PHP-FPM services
        for version in WOVar.wo_php_versions.values():
            service = f'php{version}-fpm'
            if service in apt_packages:
                WOService.stop_service(self.controller, service)
                WOService.stop_service(self.controller, f'{service}@22222')

    def _uninstall_netdata(self, packages: List[str]) -> None:
        """Uninstall Netdata using its uninstaller script.

        Args:
            packages: List to append netdata directories to
        """
        uninstaller_paths = [
            '/usr/libexec/netdata/netdata-uninstaller.sh',
            '/opt/netdata/usr/libexec/netdata/netdata-uninstaller.sh'
        ]

        for idx, path in enumerate(uninstaller_paths):
            if os.path.exists(path):
                location = "/etc/netdata" if idx == 0 else "/opt/netdata"
                Log.debug(self.controller, f"Uninstalling Netdata from {location}")

                cmd = f"bash {path} -y -f"
                errormsg = '' if idx == 0 else None
                log = False if idx == 0 else True

                WOShellExec.cmd_exec(self.controller, cmd, errormsg=errormsg, log=log)
                packages.append(location)
                break
        else:
            Log.debug(self.controller, "Netdata uninstaller not found")

        # Remove netdata MySQL user
        if WOMysql.mariadb_ping(self.controller):
            WOMysql.execute(self.controller, "DELETE FROM mysql.user WHERE User = 'netdata';")

    def _cleanup_nanorc(self) -> None:
        """Clean up nanorc configuration."""
        WOShellExec.cmd_exec(
            self.controller,
            'grep -v "nano-syntax-highlighting" /etc/nanorc > /etc/nanorc.new'
        )
        WOFileUtils.rm(self.controller, '/etc/nanorc')
        WOFileUtils.mvfile(self.controller, '/etc/nanorc.new', '/etc/nanorc')


class WOStackController(CementBaseController):
    """Main controller for stack operations."""

    class Meta:
        label = 'stack'
        stacked_on = 'base'
        stacked_type = 'nested'
        description = 'Stack command manages stack operations'
        arguments = [
            (['--all'],
                dict(help='Install all stacks at once', action='store_true')),
            (['--web'],
                dict(help='Install web stack', action='store_true')),
            (['--admin'],
                dict(help='Install admin tools stack', action='store_true')),
            (['--security'],
             dict(help='Install security tools stack', action='store_true')),
            (['--nginx'],
                dict(help='Install Nginx stack', action='store_true')),
            (['--php'],
                dict(help='Install PHP 7.2 stack', action='store_true')),
            (['--mysql'],
                dict(help='Install MySQL stack', action='store_true')),
            (['--mariadb'],
                dict(help='Install MySQL stack alias', action='store_true')),
            (['--mysqlclient'],
                dict(help='Install MySQL client for remote MySQL server',
                     action='store_true')),
            (['--mysqltuner'],
                dict(help='Install MySQLTuner stack', action='store_true')),
            (['--wpcli'],
                dict(help='Install WPCLI stack', action='store_true')),
            (['--phpmyadmin'],
                dict(help='Install PHPMyAdmin stack', action='store_true')),
            (['--composer'],
                dict(help='Install Composer stack', action='store_true')),
            (['--netdata'],
                dict(help='Install Netdata monitoring suite',
                     action='store_true')),
            (['--dashboard'],
                dict(help='Install WordOps dashboard', action='store_true')),
            (['--extplorer'],
                dict(help='Install eXtplorer file manager',
                     action='store_true')),
            (['--adminer'],
                dict(help='Install Adminer stack', action='store_true')),
            (['--fail2ban'],
                dict(help='Install Fail2ban stack', action='store_true')),
            (['--clamav'],
                dict(help='Install ClamAV stack', action='store_true')),
            (['--ufw'],
                dict(help='Install UFW stack', action='store_true')),
            (['--sendmail'],
                dict(help='Install Sendmail stack', action='store_true')),
            (['--utils'],
                dict(help='Install Utils stack', action='store_true')),
            (['--redis'],
                dict(help='Install Redis', action='store_true')),
            (['--phpredisadmin'],
                dict(help='Install phpRedisAdmin', action='store_true')),
            (['--proftpd'],
                dict(help='Install ProFTPd', action='store_true')),
            (['--ngxblocker'],
                dict(help='Install Nginx Ultimate Bad Bot Blocker',
                     action='store_true')),
            (['--cheat'],
                dict(help='Install cheat.sh', action='store_true')),
            (['--nanorc'],
                dict(help='Install nanorc syntax highlighting',
                     action='store_true')),
            (['--brotli'],
                dict(help='Enable/Disable Brotli compression for Nginx',
                     action='store_true')),
            (['--force'],
                dict(help='Force install/remove/purge without prompt',
                     action='store_true')),
        ]

        # Dynamically add PHP version arguments
        for php_version, php_number in WOVar.wo_php_versions.items():
            arguments.append(([f'--{php_version}'],
                              dict(help=f'Install PHP {php_number} stack',
                                   action='store_true')))

        usage = "wo stack (command) [options]"

    @expose(hide=True)
    def default(self) -> None:
        """Default action of wo stack command."""
        self.app.args.print_help()

    def _process_install_arguments(self, pargs: Any) -> None:
        """Process and expand installation arguments.

        Args:
            pargs: Parsed command-line arguments
        """
        # Default action for stack installation
        if all(value is None or value is False for value in vars(pargs).values()):
            pargs.web = True
            pargs.admin = True
            pargs.fail2ban = True

        if getattr(pargs, 'mariadb', False):
            pargs.mysql = True

        # Handle --all flag
        if getattr(pargs, 'all', False):
            pargs.web = True
            pargs.admin = True
            for version_key in WOVar.wo_php_versions.keys():
                setattr(pargs, version_key, True)
            pargs.redis = True
            pargs.proftpd = True

        # Handle --web stack
        if getattr(pargs, 'web', False):
            pargs.php = True
            pargs.nginx = True
            pargs.mysql = True
            pargs.wpcli = True
            pargs.sendmail = True

        # Handle --admin stack
        if getattr(pargs, 'admin', False):
            pargs.web = True
            pargs.adminer = True
            pargs.phpmyadmin = True
            pargs.composer = True
            pargs.utils = True
            pargs.netdata = True
            pargs.dashboard = True
            pargs.phpredisadmin = True
            pargs.extplorer = True
            pargs.cheat = True
            pargs.nanorc = True

        # Handle --security stack
        if getattr(pargs, 'security', False):
            pargs.fail2ban = True
            pargs.clamav = True
            pargs.ngxblocker = True

        # Handle --php flag (install default PHP version)
        if getattr(pargs, 'php', False):
            if self.app.config.has_section('php'):
                config_php_ver = self.app.config.get('php', 'version')
                current_php = config_php_ver.replace(".", "")
                setattr(pargs, f'php{current_php}', True)

    def _check_php_installed(self) -> bool:
        """Check if any PHP version is installed.

        Returns:
            True if any PHP version is installed, False otherwise
        """
        return any(
            WOAptGet.is_installed(self, f'php{version}-fpm')
            for version in WOVar.wo_php_versions.values()
        )

    @expose(help="Install packages")
    def install(self, packages: Optional[List[List[str]]] = None,
                apt_packages: Optional[List[str]] = None,
                disp_msg: bool = True) -> int:
        """Start installation of packages.

        Args:
            packages: List of download packages [url, dest, name]
            apt_packages: List of APT package names
            disp_msg: Whether to display messages

        Returns:
            0 on success, self.msg list if disp_msg is False
        """
        if packages is None:
            packages = []
        if apt_packages is None:
            apt_packages = []

        self.msg = []
        pargs = self.app.pargs

        try:
            # Process arguments
            self._process_install_arguments(pargs)

            # Create package manager and installer
            pkg_manager = PackageManager(self)
            pkg_manager.apt_packages = apt_packages
            pkg_manager.packages = packages

            installer = StackComponentInstaller(self, pkg_manager)

            # Install components based on arguments
            if getattr(pargs, 'nginx', False):
                installer.install_nginx()

            if getattr(pargs, 'redis', False):
                installer.install_redis()

            # Install PHP versions
            for parg_version, version in WOVar.wo_php_versions.items():
                if getattr(pargs, parg_version, False):
                    installer.install_php_version(parg_version, version)

            # MySQL/MariaDB
            if getattr(pargs, 'mysql', False):
                pargs.mysqltuner = True
                installer.install_mysql()

            if getattr(pargs, 'mysqlclient', False):
                installer.install_mysql_client()

            # Other components
            if getattr(pargs, 'wpcli', False):
                installer.install_wpcli()

            if getattr(pargs, 'fail2ban', False):
                installer.install_fail2ban()

            if getattr(pargs, 'clamav', False):
                installer.install_clamav()

            if getattr(pargs, 'ufw', False):
                installer.install_ufw()

            if getattr(pargs, 'sendmail', False):
                installer.install_sendmail()

            if getattr(pargs, 'proftpd', False):
                installer.install_proftpd()

            # Brotli compression
            if getattr(pargs, 'brotli', False):
                BrotliManager.enable(self)

            # Admin tools
            if getattr(pargs, 'phpmyadmin', False):
                pargs.composer = True
                installer.install_phpmyadmin()

            if getattr(pargs, 'phpredisadmin', False):
                pargs.composer = True
                installer.install_phpredisadmin()

            if getattr(pargs, 'composer', False):
                if not WOAptGet.is_exec(self, 'php'):
                    pargs.php = True
                installer.install_composer()

            if getattr(pargs, 'adminer', False):
                installer.install_adminer()

            if getattr(pargs, 'mysqltuner', False):
                installer.install_mysqltuner()

            if getattr(pargs, 'netdata', False):
                installer.install_netdata()

            if getattr(pargs, 'dashboard', False):
                installer.install_dashboard()

            if getattr(pargs, 'extplorer', False):
                installer.install_extplorer()

            if getattr(pargs, 'ngxblocker', False):
                if not WOAptGet.is_exec(self, 'nginx'):
                    pargs.nginx = True
                installer.install_ngxblocker()

            if getattr(pargs, 'cheat', False):
                installer.install_cheat()

            if getattr(pargs, 'nanorc', False):
                installer.install_nanorc()

            # Utils
            if getattr(pargs, 'utils', False):
                if not WOMysql.mariadb_ping(self):
                    pargs.mysql = True
                if not self._check_php_installed():
                    pargs.php = True
                installer.install_utils()

        except Exception as e:
            Log.debug(self, f"Error during package preparation: {e}")
            raise

        # Install packages
        if pkg_manager.apt_packages or pkg_manager.packages:
            pre_stack(self)

            if pkg_manager.apt_packages:
                Log.debug(self, "Calling pre_pref")
                pre_pref(self, pkg_manager.apt_packages)
                Log.wait(self, "Updating apt-cache          ")
                WOAptGet.update(self)
                Log.valide(self, "Updating apt-cache          ")
                Log.wait(self, "Installing APT packages     ")
                WOAptGet.install(self, pkg_manager.apt_packages)
                Log.valide(self, "Installing APT packages     ")
                post_pref(self, pkg_manager.apt_packages, [])

            if pkg_manager.packages:
                Log.debug(self, f"Downloading following: {pkg_manager.packages}")
                WODownload.download(self, pkg_manager.packages)
                Log.debug(self, "Calling post_pref")
                Log.wait(self, "Configuring packages")
                post_pref(self, [], pkg_manager.packages)
                Log.valide(self, "Configuring packages")

            if disp_msg:
                if self.msg:
                    for msg in self.msg:
                        Log.info(self, Log.ENDC + msg)
                Log.info(self, "Successfully installed packages")
            else:
                return self.msg
        return 0

    @expose(help="Remove packages")
    def remove(self) -> None:
        """Start removal of packages."""
        pargs = self.app.pargs

        # Check if any arguments provided
        if all(value is None or value is False for value in vars(pargs).values()):
            self.app.args.print_help()
            return

        # Handle Brotli separately
        if getattr(pargs, 'brotli', False):
            BrotliManager.disable(self)
            return

        # Execute removal
        remover = StackRemover(self, purge=False)
        remover.execute_removal(pargs)

    @expose(help="Purge packages")
    def purge(self) -> None:
        """Start purging of packages."""
        pargs = self.app.pargs

        # Check if any arguments provided
        if all(value is None or value is False for value in vars(pargs).values()):
            self.app.args.print_help()
            return

        # Execute purge
        remover = StackRemover(self, purge=True)
        remover.execute_removal(pargs)


def load(app: Any) -> None:
    """Load the stack plugin and register controllers.

    Args:
        app: The Cement application instance
    """
    # Register the plugin class
    app.handler.register(WOStackController)
    app.handler.register(WOStackStatusController)
    app.handler.register(WOStackMigrateController)
    app.handler.register(WOStackUpgradeController)

    # Register hook to run after arguments are parsed
    app.hook.register('post_argument_parsing', wo_stack_hook)
