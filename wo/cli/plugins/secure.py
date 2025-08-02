import getpass
import os

from cement.core.controller import CementBaseController, expose

from wo.core.fileutils import WOFileUtils
from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.random import RANDOM
from wo.core.services import WOService
from wo.core.shellexec import WOShellExec
from wo.core.template import WOTemplate
from wo.core.variables import WOVar
from wo.core.domainvalidate import WODomain
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
            'adjust settings for backend and to harden server security.')
        arguments = [
            (['--domain'],
                dict(help='secure a domain', action='store', nargs='?')),
            (['--wl'],
                dict(help='whitelist IPs for the domain', action='store', nargs='+')),
            (['--sshport'], dict(
                help='set custom ssh port', action='store_true')),
            (['--ssh'], dict(
                help='harden ssh security', action='store_true')),
            (['--allowpassword'], dict(
                help='allow password authentification '
                'when hardening ssh security', action='store_true')),
            (['--force'],
                dict(help='force execution without being prompt',
                     action='store_true')),
            (['user_input'],
                dict(help='user input', nargs='?', default=None)),
            (['user_pass'],
                dict(help='user pass', nargs='?', default=None))]
        usage = "wo secure [options]"

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        if pargs.wl and not pargs.domain:
            Log.error(self, "--wl requires --domain")
        if pargs.domain:
            self.secure_domain()
        if pargs.sshport:
            self.secure_ssh_port()
        if pargs.ssh:
            self.secure_ssh()

    @expose(hide=True)
    def secure_domain(self):
        """Secure a domain with HTTP auth or IP whitelisting"""
        pargs = self.app.pargs
        if not pargs.domain:
            Log.error(self, "Please provide a domain name with --domain option")
        wo_domain = WODomain.validate(self, pargs.domain)
        site_info = getSiteInfo(self, wo_domain)
        if not site_info:
            Log.error(self, "site {0} does not exist".format(wo_domain))

        webroot = site_info.site_path
        wp_site = 'wp' in site_info.site_type

        acl_dir = '/etc/nginx/acls'
        os.makedirs(acl_dir, exist_ok=True)
        snippet = os.path.join(acl_dir, f'secure-{wo_domain}.conf')
        vhost_path = os.path.join('/etc/nginx/sites-available', wo_domain)

        if pargs.wl:
            data = dict(is_wp=wp_site, ips=pargs.wl)
            WOTemplate.deploy(self, snippet, 'secure.mustache', data)
            self._ensure_acl_include(vhost_path, webroot, wo_domain)
            WOGit.add(self, ['/etc/nginx'], msg=f"Whitelisted IPs for {wo_domain}")
            if not WOService.reload_service(self, 'nginx'):
                Log.error(self, "service nginx reload failed. check issues with `nginx -t` command")
            Log.info(self, f"Successfully secured {wo_domain} with IP whitelist")
            return

        passwd = RANDOM.long(self)
        if not pargs.user_input:
            username = input("Provide HTTP authentication user name [{0}] :".format(WOVar.wo_user))
            if username == "":
                username = WOVar.wo_user
        else:
            username = pargs.user_input

        if not pargs.user_pass:
            password = getpass.getpass("Provide HTTP authentication password [{0}] :".format(passwd))
            if password == "":
                password = passwd
        else:
            password = pargs.user_pass

        htpasswd_file = os.path.join(acl_dir, f'htpasswd-{wo_domain}')
        WOShellExec.cmd_exec(
            self,
            "printf \"{user}:$(openssl passwd -apr1 {pw} 2> /dev/null)\\n\" > {path} 2>/dev/null".format(
                user=username, pw=password, path=htpasswd_file),
            log=False)

        data = dict(is_wp=wp_site, htpasswd=htpasswd_file)
        WOTemplate.deploy(self, snippet, 'secure.mustache', data)
        self._ensure_acl_include(vhost_path, webroot, wo_domain)
        WOGit.add(self, ['/etc/nginx'], msg=f"Secured {wo_domain} with basic auth")

        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, "service nginx reload failed. check issues with `nginx -t` command")

        Log.info(self, f"Successfully secured {wo_domain}")

    def _ensure_acl_include(self, vhost_path, webroot, domain):
        acl_include = f"    include /etc/nginx/acls/secure-{domain}.conf;\n"
        include_marker = f"include {webroot}/conf/nginx/*.conf;"
        if not os.path.exists(vhost_path):
            return
        with open(vhost_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if any(acl_include.strip() == line.strip() for line in lines):
            return
        for i, line in enumerate(lines):
            if include_marker in line:
                lines.insert(i, acl_include)
                break
        else:
            for i, line in enumerate(lines):
                if line.strip().startswith('location'):
                    lines.insert(i, acl_include)
                    break
            else:
                lines.append(acl_include)
        with open(vhost_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    @expose(hide=True)
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

    @expose(hide=True)
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
