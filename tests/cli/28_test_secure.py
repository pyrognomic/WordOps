from unittest import mock, TestCase
import importlib
import os
import re


class CliTestCaseSecure(TestCase):

    def _write_vhost(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write("server {\n    # acl start\n    # acl end\n}\n")

    def test_secure_and_clear_domain(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'pkg_resources': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))

            vhost_path = '/etc/nginx/sites-available/example.com'
            acl_path = '/etc/nginx/acls/htpasswd-example-com'
            self._write_vhost(vhost_path)
            os.makedirs('/etc/nginx/acls', exist_ok=True)

            def fake_cmd(self, cmd, log=True):
                with open(acl_path, 'w', encoding='utf-8') as fh:
                    fh.write('user:pass\n')
                return 0

            fake_site_funcs.getSiteInfo.return_value = mock.Mock(
                site_type='wp',
                cache_type='basic',
                php_version='8.1',
            )

            pargs = mock.Mock(domain='example.com', clear=False,
                               http_user='user', http_pass='pass',
                               sshport=False, ssh=False,
                               allowpassword=False, force=False)
            controller = secure_mod.WOSecureController()
            controller.app = mock.Mock(pargs=pargs)

            with mock.patch.object(secure_mod.WOShellExec, 'cmd_exec', fake_cmd), \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add'):
                controller.secure_domain()

            with open(vhost_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'map $uri $require_auth' in content
            assert 'auth_basic_user_file /etc/nginx/acls/htpasswd-example-com' in content
            assert os.path.exists(acl_path)

            pargs.clear = True
            controller.secure_domain()

            with open(vhost_path, 'r', encoding='utf-8') as f:
                cleared = f.read()
            assert 'map $uri $require_auth' not in cleared
            assert 'auth_basic_user_file' not in cleared
            assert not os.path.exists(acl_path)

