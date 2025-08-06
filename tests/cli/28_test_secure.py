from wo.cli.main import WOTestApp
from unittest import mock, TestCase
import importlib


class CliTestCaseSecure(TestCase):

    def test_secure_domain_password(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            with mock.patch.object(secure_mod.WOShellExec, 'cmd_exec'), \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add'), \
                 mock.patch.object(secure_mod.os, 'makedirs'), \
                 mock.patch.object(secure_mod.WOSecureController, '_update_map_block') as mock_map, \
                 mock.patch.object(secure_mod.WOSecureController, '_insert_acl_block') as mock_acl:
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='wp')
                with WOTestApp(argv=['secure', '--domain', 'example.com', 'user', 'pass']) as app:
                    secure_mod.load(app)
                    app.run()
                    mock_map.assert_called_with('/etc/nginx/sites-available/example.com', ['~^/wp-login\\.php     1;', '~^/wp-admin/         1;'], 'require_auth_example_com')
                    mock_acl.assert_called_with('/etc/nginx/sites-available/example.com', 'example-com', 'require_auth_example_com')

    def test_secure_domain_whitelist(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            with mock.patch.object(secure_mod.WOShellExec, 'cmd_exec'), \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add'), \
                 mock.patch.object(secure_mod.os, 'makedirs'), \
                 mock.patch.object(secure_mod.WOSecureController, '_update_map_block') as mock_map, \
                 mock.patch.object(secure_mod.WOSecureController, '_insert_acl_block') as mock_acl:
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='html')
                with WOTestApp(argv=['secure', '--domain', 'example.com', '--path', '/admin', 'user', 'pass']) as app:
                    secure_mod.load(app)
                    app.run()
                    mock_map.assert_called_with('/etc/nginx/sites-available/example.com', ['~^/admin     1;'])
                    mock_acl.assert_called_with('/etc/nginx/sites-available/example.com', 'example-com')

    def test_clear_acl_removes_htpasswd_and_commits(self):
        fake_site_funcs = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            vhost_path = '/etc/nginx/sites-available/example.com'
            slug = 'example-com'
            htpasswd_path = f'/etc/nginx/acls/htpasswd-{slug}'
            vhost_content = (
                'map $uri $require_auth {\n' '    default              1;\n' '}\n'
                '# acl start\n'
                '    auth_basic           "Restricted"      if=$require_auth;\n'
                '    auth_basic_user_file /etc/nginx/acls/htpasswd-example-com  if=$require_auth;\n'
                '# acl end\n'
            )
            with mock.patch.object(secure_mod.os.path, 'exists', side_effect=lambda p: p in [vhost_path, htpasswd_path]), \
                 mock.patch('builtins.open', mock.mock_open(read_data=vhost_content)), \
                 mock.patch.object(secure_mod.os, 'remove') as mock_remove, \
                 mock.patch.object(secure_mod.WOGit, 'add') as mock_git_add, \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True):
                with WOTestApp(argv=['secure', '--domain', 'example.com', '--clear']) as app:
                    secure_mod.load(app)
                    app.run()
                    mock_remove.assert_called_with(htpasswd_path)
                    mock_git_add.assert_called_with(mock.ANY, ['/etc/nginx'], msg='Removed basic auth for example.com')

                    mock_map.assert_called_with('/etc/nginx/sites-available/example.com', ['~^/admin     1;'], 'require_auth_example_com')
                    mock_acl.assert_called_with('/etc/nginx/sites-available/example.com', 'example-com', 'require_auth_example_com')
