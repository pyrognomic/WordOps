from wo.cli.main import WOTestApp
from unittest import mock, TestCase
import importlib


class CliTestCaseSecure(TestCase):

    def test_secure_domain_renders_protected(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            with mock.patch.object(secure_mod.WOShellExec, 'cmd_exec') as mock_exec, \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add') as mock_git_add, \
                 mock.patch.object(secure_mod.os, 'makedirs'), \
                 mock.patch.object(secure_mod.WOTemplate, 'deploy') as mock_deploy:
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='wp', php_version='8.1')
                with WOTestApp(argv=['secure', '--domain', 'example.com', 'user', 'pass']) as app:
                    secure_mod.load(app)
                    app.run()
                    expected_data = {
                        'slug': 'example-com',
                        'secure': True,
                        'wp': True,
                        'php_ver': '81',
                        'pool_name': 'example-com',
                    }
                    mock_deploy.assert_called_with(mock.ANY, '/etc/nginx/acl/example-com/protected.conf', 'protected.mustache', expected_data, overwrite=True)
                    mock_exec.assert_called()
                    mock_git_add.assert_called_with(mock.ANY, ['/etc/nginx'], msg='Secured example.com with basic auth')

    def test_clear_acl_removes_credentials_and_rerenders(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            credentials = '/etc/nginx/acl/example-com/credentials'
            with mock.patch.object(secure_mod.os.path, 'exists', return_value=True), \
                 mock.patch.object(secure_mod.os, 'remove') as mock_remove, \
                 mock.patch.object(secure_mod.WOTemplate, 'deploy') as mock_deploy, \
                 mock.patch.object(secure_mod.WOGit, 'add') as mock_git_add, \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True):
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='html', php_version='8.1')
                with WOTestApp(argv=['secure', '--domain', 'example.com', '--clear']) as app:
                    secure_mod.load(app)
                    app.run()
                    expected_data = {
                        'slug': 'example-com',
                        'secure': False,
                        'wp': False,
                        'php_ver': '81',
                        'pool_name': 'example-com',
                    }
                    mock_deploy.assert_called_with(mock.ANY, '/etc/nginx/acl/example-com/protected.conf', 'protected.mustache', expected_data, overwrite=True)
                    mock_remove.assert_called_with(credentials)
                    mock_git_add.assert_called_with(mock.ANY, ['/etc/nginx'], msg='Removed basic auth for example.com')
