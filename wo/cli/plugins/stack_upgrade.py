import os
import shutil

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.stack_pref import post_pref, pre_pref, pre_stack
from wo.core.aptget import WOAptGet
from wo.core.download import WODownload
from wo.core.extract import WOExtract
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.shellexec import WOShellExec
from wo.core.variables import WOVar
from wo.core.services import WOService
from wo.core.mysql import WOMysql


class WOStackUpgradeController(CementBaseController):
    class Meta:
        label = 'upgrade'
        stacked_on = 'stack'
        stacked_type = 'nested'
        description = ('Upgrade stack safely')
        arguments = [
            (['--all'],
                dict(help='Upgrade all stack', action='store_true')),
            (['--web'],
                dict(help='Upgrade web stack', action='store_true')),
            (['--admin'],
                dict(help='Upgrade admin tools stack', action='store_true')),
            (['--security'],
                dict(help='Upgrade security stack', action='store_true')),
            (['--nginx'],
                dict(help='Upgrade Nginx stack', action='store_true')),
            (['--php'],
                dict(help='Upgrade PHP stack', action='store_true')),
            (['--mysql'],
                dict(help='Upgrade MySQL stack', action='store_true')),
            (['--mariadb'],
                dict(help='Upgrade MySQL stack alias',
                     action='store_true')),
            (['--wpcli'],
                dict(help='Upgrade WPCLI', action='store_true')),
            (['--redis'],
                dict(help='Upgrade Redis', action='store_true')),
            (['--netdata'],
                dict(help='Upgrade Netdata', action='store_true')),
            (['--fail2ban'],
                dict(help='Upgrade Fail2Ban', action='store_true')),
            (['--dashboard'],
                dict(help='Upgrade WordOps Dashboard', action='store_true')),
            (['--composer'],
             dict(help='Upgrade Composer', action='store_true')),
            (['--mysqltuner'],
             dict(help='Upgrade MySQLTuner', action='store_true')),
            (['--phpmyadmin'],
             dict(help='Upgrade phpMyAdmin', action='store_true')),
            (['--adminer'],
             dict(help='Upgrade Adminer', action='store_true')),
            (['--ngxblocker'],
             dict(help='Upgrade Nginx Bad Bot Blocker', action='store_true')),
            (['--no-prompt'],
                dict(help="Upgrade Packages without any prompt",
                     action='store_true')),
            (['--force'],
                dict(help="Force Packages upgrade without any prompt",
                     action='store_true')),
        ]
        for php_version, php_number in WOVar.wo_php_versions.items():
            arguments.append(([f'--{php_version}'],
                              dict(help=f'Upgrade PHP {php_number} stack',
                                   action='store_true')))

    @expose(hide=True)
    def default(self, disp_msg=False):
        # All package update
        apt_packages = []
        packages = []
        self.msg = []
        pargs = self.app.pargs
        wo_phpmyadmin = WODownload.pma_release(self)
        if all(value is None or value is False for value in vars(pargs).values()):
            pargs.web = True
            pargs.admin = True
            pargs.security = True

        if pargs.mariadb:
            pargs.mysql = True

        if pargs.php:
            if self.app.config.has_section('php'):
                config_php_ver = self.app.config.get(
                    'php', 'version')
                current_php = config_php_ver.replace(".", "")
                setattr(self.app.pargs, 'php{0}'.format(current_php), True)

        if pargs.all:
            pargs.web = True
            pargs.admin = True
            pargs.security = True
            pargs.redis = True

        if pargs.web:
            pargs.nginx = True
            pargs.php74 = True
            pargs.php80 = True
            pargs.php81 = True
            pargs.php82 = True
            pargs.php83 = True
            pargs.php84 = True
            pargs.mysql = True
            pargs.wpcli = True

        if pargs.admin:
            pargs.netdata = True
            pargs.composer = True
            pargs.dashboard = True
            pargs.phpmyadmin = True
            pargs.wpcli = True
            pargs.adminer = True
            pargs.mysqltuner = True

        if pargs.security:
            pargs.ngxblocker = True
            pargs.fail2ban = True

        # nginx
        if pargs.nginx:
            if WOAptGet.is_installed(self, 'nginx-custom'):
                apt_packages = apt_packages + WOVar.wo_nginx
            else:
                if os.path.isfile('/usr/sbin/nginx'):
                    Log.info(self, "Updating Nginx templates")
                    post_pref(self, WOVar.wo_nginx, [])
                else:
                    Log.info(self, "Nginx Stable is not already installed")

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
                Log.debug(self, f"Setting apt_packages variable for PHP {version}")
                if WOAptGet.is_installed(self, f'php{version}-fpm'):
                    apt_packages = apt_packages + wo_vars[parg_version] + WOVar.wo_php_extra
                else:
                    Log.debug(self, f"PHP {version} not installed")
                    Log.info(self, f"PHP {version} not installed")

        # mysql
        if pargs.mysql:
            if WOMysql.mariadb_ping(self):
                apt_packages = apt_packages + WOVar.wo_mysql

        # redis
        if pargs.redis:
            if WOAptGet.is_installed(self, 'redis-server'):
                apt_packages = apt_packages + ['redis-server']

        # fail2ban
        if pargs.fail2ban:
            if WOAptGet.is_installed(self, 'fail2ban'):
                apt_packages = apt_packages + ['fail2ban']

        # wp-cli
        if pargs.wpcli:
            if os.path.isfile('/usr/local/bin/wp'):
                packages = packages + [[f"{WOVar.wpcli_url}",
                                        "/usr/local/bin/wp",
                                        "WP-CLI"]]
            else:
                Log.info(self, "WPCLI is not installed with WordOps")

        # netdata
        if pargs.netdata:
            # detect static binaries install
            if (os.path.isdir('/opt/netdata') or
                    os.path.isdir('/etc/netdata')):
                packages = packages + [[
                    f"{WOVar.netdata_script_url}",
                    '/var/lib/wo/tmp/kickstart.sh', 'Netdata']]
            else:
                Log.info(self, 'Netdata is not installed')

        # wordops dashboard
        if pargs.dashboard:
            if (os.path.isfile('/var/www/22222/htdocs/index.php') or
                    os.path.isfile('/var/www/22222/htdocs/index.html')):
                packages = packages + [[
                    "https://github.com/WordOps/wordops-dashboard/"
                    "releases/download/v{0}/wordops-dashboard.tar.gz"
                    .format(WOVar.wo_dashboard),
                    "/var/lib/wo/tmp/wo-dashboard.tar.gz",
                    "WordOps Dashboard"]]
            else:
                Log.info(self, 'WordOps dashboard is not installed')

        # phpmyadmin
        if pargs.phpmyadmin:
            if os.path.isdir('/var/www/22222/htdocs/db/pma'):
                packages = packages + [[
                    "https://files.phpmyadmin.net"
                    "/phpMyAdmin/{0}/phpMyAdmin-{0}-"
                    "all-languages.tar.gz"
                    .format(wo_phpmyadmin),
                    "/var/lib/wo/tmp/pma.tar.gz",
                    "PHPMyAdmin"]]
            else:
                Log.info(self, "phpMyAdmin isn't installed")

        # adminer
        if pargs.adminer:
            if os.path.isfile("{0}22222/htdocs/db/"
                              "adminer/index.php"
                              .format(WOVar.wo_webroot)):
                Log.debug(self, "Setting packages variable for Adminer ")
                packages = packages + [[
                    "https://www.adminer.org/latest.php",
                    "{0}22222/"
                    "htdocs/db/adminer/index.php"
                    .format(WOVar.wo_webroot),
                    "Adminer"],
                    ["https://raw.githubusercontent.com"
                     "/vrana/adminer/master/designs/"
                     "pepa-linha/adminer.css",
                     "{0}22222/"
                     "htdocs/db/adminer/adminer.css"
                     .format(WOVar.wo_webroot),
                     "Adminer theme"]]
            else:
                Log.debug(self, "Adminer isn't installed")
                Log.info(self, "Adminer isn't installed")

        # composer
        if pargs.composer:
            if os.path.isfile('/usr/local/bin/composer'):
                packages = packages + [[
                    "https://getcomposer.org/installer",
                    "/var/lib/wo/tmp/composer-install",
                    "Composer"]]
            else:
                Log.info(self, "Composer isn't installed")

        # mysqltuner
        if pargs.mysqltuner:
            if WOAptGet.is_exec(self, 'mysqltuner'):
                Log.debug(self, "Setting packages variable "
                          "for MySQLTuner ")
                packages = packages + [["https://raw."
                                        "githubusercontent.com/"
                                        "major/MySQLTuner-perl"
                                        "/master/mysqltuner.pl",
                                        "/usr/bin/mysqltuner",
                                        "MySQLTuner"]]

        # ngxblocker
        if pargs.ngxblocker:
            if os.path.exists('/usr/local/sbin/install-ngxblocker'):
                packages = packages + [[
                    'https://raw.githubusercontent.com/mitchellkrogza/'
                    'nginx-ultimate-bad-bot-blocker/master/update-ngxblocker',
                    '/usr/local/sbin/update-ngxblocker',
                    'ngxblocker'
                ]]

        if not apt_packages and not packages:
            self.app.args.print_help()
        else:
            pre_stack(self)
            if apt_packages:
                # Check if critical packages are being upgraded
                critical_packages = ['redis-server', 'nginx-custom', 'mariadb-server']
                for version in WOVar.wo_php_versions.values():
                    critical_packages.append(f'php{version}-fpm')

                if any(pkg in apt_packages for pkg in critical_packages):
                    Log.warn(
                        self, "Your sites may be down for few seconds if "
                        "you are upgrading Nginx, PHP-FPM, MariaDB or Redis")
                # Check prompt
                if not (pargs.no_prompt or pargs.force):
                    start_upgrade = input("Do you want to continue:[y/N]")
                    if start_upgrade != "Y" and start_upgrade != "y":
                        Log.error(self, "Not starting package update")
                # additional pre_pref
                if "nginx-custom" in apt_packages:
                    pre_pref(self, WOVar.wo_nginx)
                Log.wait(self, "Updating APT cache")
                # apt-get update
                WOAptGet.update(self)
                Log.valide(self, "Updating APT cache")

                # check if nginx upgrade is blocked
                if os.path.isfile(
                        '/etc/apt/preferences.d/nginx-block'):
                    post_pref(self, WOVar.wo_nginx, [], True)
                # redis pre_pref
                if "redis-server" in apt_packages:
                    pre_pref(self, WOVar.wo_redis)
                # upgrade packages
                WOAptGet.install(self, apt_packages)
                Log.wait(self, "Configuring APT Packages")
                post_pref(self, apt_packages, [], True)
                Log.valide(self, "Configuring APT Packages")
                # Post Actions after package updates

            if packages:
                if WOAptGet.is_selected(self, 'WP-CLI', packages):
                    WOFileUtils.rm(self, '/usr/local/bin/wp')

                if WOAptGet.is_selected(self, 'Netdata', packages):
                    WOFileUtils.rm(self, '/var/lib/wo/tmp/kickstart.sh')

                if WOAptGet.is_selected(self, 'ngxblocker', packages):
                    WOFileUtils.rm(self, '/usr/local/sbin/update-ngxblocker')

                if WOAptGet.is_selected(self, 'WordOps Dashboard', packages):
                    if os.path.isfile('/var/www/22222/htdocs/index.php'):
                        WOFileUtils.rm(self, '/var/www/22222/htdocs/index.php')
                    if os.path.isfile('/var/www/22222/htdocs/index.html'):
                        WOFileUtils.rm(
                            self, '/var/www/22222/htdocs/index.html')

                Log.debug(self, "Downloading following: {0}".format(packages))
                WODownload.download(self, packages)

                if WOAptGet.is_selected(self, 'WP-CLI', packages):
                    WOFileUtils.chmod(self, "/usr/local/bin/wp", 0o775)

                if WOAptGet.is_selected(self, 'ngxblocker', packages):
                    if os.path.exists('/etc/nginx/conf.d/variables-hash.conf'):
                        WOFileUtils.rm(
                            self, '/etc/nginx/conf.d/variables-hash.conf')
                    WOFileUtils.chmod(
                        self, '/usr/local/sbin/update-ngxblocker', 0o775)
                    WOShellExec.cmd_exec(
                        self, '/usr/local/sbin/update-ngxblocker -nq')

                if WOAptGet.is_selected(self, 'MySQLTuner', packages):
                    WOFileUtils.chmod(self, "/usr/bin/mysqltuner", 0o775)
                    if os.path.exists('/usr/local/bin/mysqltuner'):
                        WOFileUtils.rm(self, '/usr/local/bin/mysqltuner')

                # Netdata
                if WOAptGet.is_selected(self, 'Netdata', packages):
                    WOService.stop_service(self, 'netdata')
                    if os.path.exists('/opt/netdata/usr/libexec/netdata/netdata-uninstaller.sh'):
                        WOShellExec.cmd_exec(self,
                                             "/opt/netdata/usr/libexec/"
                                             "netdata/netdata-uninstaller.sh --yes --force",
                                             log=False)
                    Log.wait(self, "Upgrading Netdata")
                    # detect static binaries install
                    WOShellExec.cmd_exec(
                        self,
                        "bash /var/lib/wo/tmp/kickstart.sh "
                        "--dont-wait --no-updates --stable-channel "
                        "--reinstall-even-if-unsafe",
                        errormsg='', log=False)
                    Log.valide(self, "Upgrading Netdata")

                if WOAptGet.is_selected(self, 'WordOps Dashboard', packages):
                    post_pref(
                        self, [], [["https://github.com/WordOps"
                                    "/wordops-dashboard/"
                                    "releases/download/v{0}/"
                                    "wordops-dashboard.tar.gz"
                                    .format(WOVar.wo_dashboard),
                                    "/var/lib/wo/tmp/wo-dashboard.tar.gz",
                                    "WordOps Dashboard"]])

                if WOAptGet.is_selected(self, 'Composer', packages):
                    Log.wait(self, "Upgrading Composer")
                    try:
                        if WOShellExec.cmd_exec(
                                self, '/usr/bin/php -v'):
                            WOShellExec.cmd_exec(
                                self, "php -q /var/lib/wo"
                                "/tmp/composer-install "
                                "--install-dir=/var/lib/wo/tmp/")

                        if not os.path.isfile('/var/lib/wo/tmp/composer.phar'):
                            raise FileNotFoundError("Composer installation failed - composer.phar not created")

                        shutil.copyfile('/var/lib/wo/tmp/composer.phar',
                                        '/usr/local/bin/composer')
                        WOFileUtils.chmod(self, "/usr/local/bin/composer", 0o775)
                        Log.valide(self, "Upgrading Composer    ")
                    except Exception as e:
                        Log.failed(self, "Upgrading Composer    ")
                        Log.error(self, f"Composer upgrade failed: {e}")
                        Log.debug(self, f"Exception details: {str(e)}")

                if WOAptGet.is_selected(self, 'PHPMyAdmin', packages):
                    Log.wait(self, "Upgrading phpMyAdmin")

                    pma_path = f'{WOVar.wo_webroot}22222/htdocs/db/pma'
                    backup_path = f'{pma_path}.backup'
                    config_src = f'{pma_path}/config.inc.php'
                    config_dst = f'/var/lib/wo/tmp/phpMyAdmin-{wo_phpmyadmin}-all-languages/config.inc.php'

                    try:
                        # Extract new version
                        WOExtract.extract(self, '/var/lib/wo/tmp/pma.tar.gz',
                                          '/var/lib/wo/tmp/')

                        # Backup old phpMyAdmin
                        if os.path.isdir(pma_path):
                            Log.debug(self, f"Creating backup of phpMyAdmin at {backup_path}")
                            shutil.copytree(pma_path, backup_path)

                        # Copy config file if it exists
                        if os.path.isfile(config_src):
                            shutil.copyfile(config_src, config_dst)
                        else:
                            Log.warn(self, "phpMyAdmin config file not found, upgrade may require reconfiguration")

                        # Remove old installation
                        WOFileUtils.rm(self, pma_path)

                        # Move new version
                        shutil.move(f'/var/lib/wo/tmp/phpMyAdmin-{wo_phpmyadmin}-all-languages/',
                                    f'{pma_path}/')

                        # Set proper ownership
                        WOFileUtils.chown(self, f"{WOVar.wo_webroot}22222/htdocs",
                                          'www-data',
                                          'www-data', recursive=True)

                        # Remove backup on success
                        if os.path.isdir(backup_path):
                            Log.debug(self, "Removing backup after successful upgrade")
                            shutil.rmtree(backup_path)

                        Log.valide(self, "Upgrading phpMyAdmin")

                    except Exception as e:
                        Log.failed(self, "Upgrading phpMyAdmin")
                        Log.error(self, f"phpMyAdmin upgrade failed: {e}")
                        Log.debug(self, f"Exception details: {str(e)}")

                        # Restore from backup if exists
                        if os.path.isdir(backup_path):
                            try:
                                if os.path.isdir(pma_path):
                                    shutil.rmtree(pma_path)
                                shutil.copytree(backup_path, pma_path)
                                Log.info(self, "Restored phpMyAdmin from backup")
                                shutil.rmtree(backup_path)
                            except Exception as restore_error:
                                Log.error(self, f"Failed to restore backup: {restore_error}")
                        else:
                            Log.error(self, "No backup available for restoration")
                if os.path.exists('{0}22222/htdocs'.format(WOVar.wo_webroot)):
                    WOFileUtils.chown(self, "{0}22222/htdocs"
                                      .format(WOVar.wo_webroot),
                                      'www-data',
                                      'www-data', recursive=True)

            Log.info(self, "Successfully updated packages")
