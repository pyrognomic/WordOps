import getpass
import os

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.site_functions import getSiteInfo
from wo.core.domainvalidate import WODomain
from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.random import RANDOM
from wo.core.services import WOService
from wo.core.shellexec import WOShellExec
from wo.core.template import WOTemplate
from wo.core.variables import WOVar


class WOSiteSecureController(CementBaseController):
    class Meta:
        label = 'site-secure'
        aliases = ['secure']
        stacked_on = 'site'
        stacked_type = 'nested'
        description = 'Manage HTTP basic authentication for a site.'
        arguments = [
            (['site_name'],
             dict(help='domain name to secure', nargs='?')),
            (['username'],
             dict(help='HTTP basic auth user name', nargs='?')),
            (['password'],
             dict(help='HTTP basic auth password', nargs='?')),
            (['--rm'],
             dict(help='remove HTTP basic authentication for the site',
                  action='store_true')),
        ]
        usage = 'wo site secure <domain> [<user> <pass>] [--rm]'

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs
        domain = self._get_domain(pargs)

        if pargs.rm:
            if pargs.username or pargs.password:
                Log.warn(self, 'Ignoring username/password arguments when removing basic auth.')
            self._remove_basic_auth(domain)
            return

        username, password = self._resolve_credentials(pargs)
        self._apply_basic_auth(domain, username, password)

    def _get_domain(self, pargs):
        domain = pargs.site_name
        if not domain:
            try:
                while not domain:
                    domain = input('Enter site domain: ').strip()
            except IOError as error:
                Log.debug(self, str(error))
                Log.error(self, 'Unable to read domain input.')
        domain = domain.strip()
        if not domain:
            Log.error(self, 'Please provide a valid domain name.')
        return domain

    def _apply_basic_auth(self, domain, username, password):
        wo_domain = WODomain.validate(self, domain)
        site_info = getSiteInfo(self, wo_domain)
        if not site_info:
            Log.error(self, f'site {wo_domain} does not exist')

        slug = wo_domain.replace('.', '-').lower()
        acl_dir = f'/etc/nginx/acl/{slug}'
        os.makedirs(acl_dir, exist_ok=True)
        protected = os.path.join(acl_dir, 'protected.conf')
        credentials = os.path.join(acl_dir, 'credentials')

        hashed = WOShellExec.cmd_exec_stdout(
            self,
            ['openssl', 'passwd', '-apr1', password],
            errormsg='Failed to generate HTTP authentication hash.',
            log=False,
        ).strip()
        if not hashed:
            Log.error(self, 'Failed to generate HTTP authentication hash.')

        try:
            with open(credentials, 'w', encoding='utf-8') as cred_file:
                cred_file.write(f'{username}:{hashed}\n')
        except OSError as error:
            Log.error(self, f'Failed to write HTTP authentication credentials: {error}')

        data = {
            'slug': slug,
            'secure': True,
            'wp': 'wp' in site_info.site_type,
            'php_ver': site_info.php_version.replace('.', ''),
            'pool_name': slug,
        }

        WOTemplate.deploy(self, protected, 'protected.mustache', data, overwrite=True)

        WOGit.add(self, ['/etc/nginx'], msg=f'Secured {wo_domain} with basic auth')
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, 'service nginx reload failed. check `nginx -t`')
        Log.info(self, f'Successfully secured {wo_domain}')

    def _remove_basic_auth(self, domain):
        wo_domain = WODomain.validate(self, domain)
        site_info = getSiteInfo(self, wo_domain)
        if not site_info:
            Log.error(self, f'site {wo_domain} does not exist')

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

        WOGit.add(self, ['/etc/nginx'], msg=f'Removed basic auth for {wo_domain}')
        if not WOService.reload_service(self, 'nginx'):
            Log.error(self, 'service nginx reload failed. check `nginx -t`')
        Log.info(self, f'Removed basic auth for {wo_domain}')

    def _resolve_credentials(self, pargs):
        username = pargs.username
        if not username:
            try:
                prompt = f'Provide HTTP authentication user name [{WOVar.wo_user}]: '
                username = input(prompt).strip() or WOVar.wo_user
            except IOError as error:
                Log.debug(self, str(error))
                Log.error(self, 'Unable to read username input.')

        generated_password = RANDOM.long(self)
        password = pargs.password
        if not password:
            password_prompt = f'Provide HTTP authentication password [{generated_password}]: '
            password = getpass.getpass(password_prompt) or generated_password

        return username, password
