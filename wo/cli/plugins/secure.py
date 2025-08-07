import getpass
import os

from cement.core.controller import CementBaseController, expose

from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.random import RANDOM
from wo.core.services import WOService
from wo.core.shellexec import WOShellExec
from wo.core.template import WOTemplate
from wo.core.variables import WOVar
from wo.core.domainvalidate import WODomain
from wo.core.fileutils import WOFileUtils
from wo.cli.plugins.site_functions import getSiteInfo


def wo_secure_hook(app):
    pass


class WOSecureController(CementBaseController):
    class Meta:
        label = 'secure'
        stacked_on = 'base'
        stacked_type = 'nested'
        description = (
            'Secure command provide the ability to '
            'adjust settings for backend and to harden server security.'
        )
        arguments = [
            (['--domain'],
                dict(help='secure a domain', action='store', nargs='?')),
            (['--clear'],
                dict(help='remove ACL include from vhost', action='store_true')),
            (['--sshport'],
                dict(help='set custom ssh port', action='store_true')),
            (['--ssh'],
                dict(help='harden ssh security', action='store_true')),
            (['--allowpassword'],
                dict(help='allow password authentication '
                     'when hardening ssh security', action='store_true')),
            (['--force'],
                dict(help='force execution without prompt', action='store_true')),
            (['--path'],
                dict(help='paths to secure with basic auth', action='append')),
            (['user_input'],
                dict(help='user input', nargs='?', default=None)),
            (['user_pass'],
                dict(help='user pass', nargs='?', default=None))
        ]
        usage = "wo secure [options]"

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        if pargs.clear and pargs.domain:
            self.clear_acl()
            return
        if pargs.domain:
            self.secure_domain()
        if pargs.sshport:
            self.secure_ssh_port()
        if pargs.ssh:
            self.secure_ssh()

    @expose(hide=True)
    def secure_domain(self):
        """Secure a domain with HTTP Basic Authentication"""
        pargs = self.app.pargs
        if not pargs.domain:
            Log.error(self, "Please provide a domain name with --domain option")
        wo_domain = WODomain.validate(self, pargs.domain)
        site_info = getSiteInfo(self, wo_domain)
        if not site_info:
            Log.error(self, f"site {wo_domain} does not exist")

        slug = wo_domain.replace('.', '-').lower()
        acl_dir = f'/etc/nginx/acl/{slug}'
        os.makedirs(acl_dir, exist_ok=True)
        protected = os.path.join(acl_dir, 'protected.conf')
        credentials = os.path.join(acl_dir, 'credentials')

        passwd = RANDOM.long(self)
        username = pargs.user_input or input(
            f"Provide HTTP authentication user name [{WOVar.wo_user}]: ") or WOVar.wo_user
        password = pargs.user_pass or getpass.getpass(
            f"Provide HTTP authentication password [{passwd}]: ") or passwd
        WOShellExec.cmd_exec(
            self,
            f"printf \"{username}:$(openssl passwd -apr1 {password} 2>/dev/null)\\n\" > {credentials} 2>/dev/null",
            log=False)

        data = {
            'slug': slug,
            'secure': True,
            'wp': 'wp' in site_info.site_type,
            'php_ver': site_info.php_version.replace('.', ''),
            'pool_name': slug,
        }

        WOTemplate.deploy(self, protected, 'protected.mustache', data, overwrite=True)

        WOGit.add(self, ['/etc/nginx'], msg=f"Secured {wo_domain} with basic auth")
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, "service nginx reload failed. check `nginx -t`")
        Log.info(self, f"Successfully secured {wo_domain}")

    @expose(hide=True)
    def clear_acl(self):
        """Remove HTTP Basic Authentication"""
        pargs = self.app.pargs
        wo_domain = WODomain.validate(self, pargs.domain)
        site_info = getSiteInfo(self, wo_domain)
        if not site_info:
            Log.error(self, f"site {wo_domain} does not exist")

        slug = wo_domain.replace('.', '-').lower()
        acl_dir = f'/etc/nginx/acl/{slug}'
        protected = os.path.join(acl_dir, 'protected.conf')
        credentials = os.path.join(acl_dir, 'credentials')

        data = {
            'slug': slug,
            'secure': False,
            'wp': 'wp' in site_info.site_type,
            'php_ver': site_info.php_version.replace('.', ''),
            'pool_name': slug,
        }

        WOTemplate.deploy(self, protected, 'protected.mustache', data, overwrite=True)
        if os.path.exists(credentials):
            os.remove(credentials)

        WOGit.add(self, ['/etc/nginx'], msg=f"Removed basic auth for {wo_domain}")
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, "service nginx reload failed. check `nginx -t`")
        Log.info(self, f"Removed basic auth for {wo_domain}")

    def secure_ssh(self):
        """Harden ssh security"""
        pargs = self.app.pargs
        if not pargs.force and not pargs.allowpassword:
            start_secure = input('Are you sure you to want to'
                                 ' harden SSH security ?'
                                 '\nSSH login with password will not '
                                 'be possible anymore. Please make sure '
                                 'you are already using SSH Keys.\n'
                                 'Harden SSH security [y/N]')
            if start_secure != "Y" and start_secure != "y":
                Log.error(self, "Not hardening SSH security")
        if os.path.exists('/etc/ssh'):
            WOGit.add(self, ["/etc/ssh"],
                      msg="Adding SSH into Git")
        Log.debug(self, "check if /etc/ssh/sshd_config exist")
        if os.path.isfile('/etc/ssh/sshd_config'):
            Log.debug(self, "looking for the current ssh port")
            for line in open('/etc/ssh/sshd_config', encoding='utf-8'):
                if 'Port' in line:
                    ssh_line = line.strip()
                    break
            port = (ssh_line).split(' ')
            current_ssh_port = (port[1]).strip()
            if os.getenv('SUDO_USER'):
                sudo_user = os.getenv('SUDO_USER')
            else:
                sudo_user = ''
            if pargs.allowpassword:
                wo_allowpassword = 'yes'
            else:
                wo_allowpassword = 'no'
            data = dict(sshport=current_ssh_port, allowpass=wo_allowpassword,
                        user=sudo_user)
            WOTemplate.deploy(self, '/etc/ssh/sshd_config',
                              'sshd.mustache', data)
            WOGit.add(self, ["/etc/ssh"],
                      msg="Adding changed SSH port into Git")
            if not WOService.restart_service(self, 'ssh'):
                Log.error(self, "service SSH restart failed.")
                Log.info(self, "Successfully harden SSH security")
        else:
            Log.error(self, "SSH config file not found")

    def secure_ssh_port(self):
        """Change SSH port"""
        WOGit.add(self, ["/etc/ssh"],
                  msg="Adding changed SSH port into Git")
        pargs = self.app.pargs
        if pargs.user_input:
            while ((not pargs.user_input.isdigit()) and
                   (not pargs.user_input < 65536)):
                Log.info(self, "Please enter a valid port number ")
                pargs.user_input = input("Server "
                                         "SSH port [22]:")
        if not pargs.user_input:
            port = input("Server SSH port [22]:")
            if port == "":
                port = 22
            while (not port.isdigit()) and (port != "") and (not port < 65536):
                Log.info(self, "Please Enter valid port number :")
                port = input("Server SSH port [22]:")
            pargs.user_input = port
        if WOFileUtils.grepcheck(self, '/etc/ssh/sshd_config', '#Port'):
            WOShellExec.cmd_exec(self, "sed -i \"s/#Port.*/Port "
                                 "{port}/\" /etc/ssh/sshd_config"
                                 .format(port=pargs.user_input))
        else:
            WOShellExec.cmd_exec(self, "sed -i \"s/Port.*/Port "
                                 "{port}/\" /etc/ssh/sshd_config"
                                 .format(port=pargs.user_input))
        # allow new ssh port if ufw is enabled
        if os.path.isfile('/etc/ufw/ufw.conf'):
            # add rule for proftpd with UFW
            if WOFileUtils.grepcheck(
                    self, '/etc/ufw/ufw.conf', 'ENABLED=yes'):
                try:
                    WOShellExec.cmd_exec(
                        self, 'ufw limit {0}'.format(pargs.user_input))
                    WOShellExec.cmd_exec(
                        self, 'ufw reload')
                except Exception as e:
                    Log.debug(self, "{0}".format(e))
                    Log.error(self, "Unable to add UFW rule")
        # add ssh into git
        WOGit.add(self, ["/etc/ssh"],
                  msg="Adding changed SSH port into Git")
        # restart ssh service
        if not WOService.restart_service(self, 'ssh'):
            Log.error(self, "service SSH restart failed.")
        Log.info(self, "Successfully changed SSH port to {port}"
                 .format(port=pargs.user_input))


def load(app):
    app.handler.register(WOSecureController)
    app.hook.register('post_argument_parsing', wo_secure_hook)
