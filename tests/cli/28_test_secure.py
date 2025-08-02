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
            with mock.patch.object(secure_mod.WOShellExec, 'cmd_exec') as mock_cmd, \
                 mock.patch.object(secure_mod.WOTemplate, 'deploy') as mock_deploy, \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add'), \
                 mock.patch.object(secure_mod.os, 'makedirs'), \
                 mock.patch.object(secure_mod.os.path, 'exists', return_value=True), \
                 mock.patch('wo.cli.plugins.secure.open', mock.mock_open(read_data='existing\n    include /var/www/example.com/conf/nginx/*.conf;\n')):
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='wp')
                with WOTestApp(argv=['secure', '--domain', 'example.com', 'user', 'pass']) as app:
                    secure_mod.load(app)
                    app.run()
                    mock_deploy.assert_called_with(mock.ANY, '/etc/nginx/acls/secure-example.com.conf', 'secure.mustache', mock.ANY)

    def test_secure_domain_whitelist(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure'))
            with mock.patch.object(secure_mod.WOTemplate, 'deploy') as mock_deploy, \
                 mock.patch.object(secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(secure_mod.WOGit, 'add'), \
                 mock.patch.object(secure_mod.os, 'makedirs'), \
                 mock.patch.object(secure_mod.os.path, 'exists', return_value=True), \
                 mock.patch('wo.cli.plugins.secure.open', mock.mock_open(read_data='existing\n    include /var/www/example.com/conf/nginx/*.conf;\n')):
                fake_site_funcs.getSiteInfo.return_value = mock.Mock(site_path='/var/www/example.com', site_type='html')
                with WOTestApp(argv=['secure', '--domain', 'example.com', '--wl', '127.0.0.1']) as app:
                    secure_mod.load(app)
                    app.run()
                    mock_deploy.assert_called_with(mock.ANY, '/etc/nginx/acls/secure-example.com.conf', 'secure.mustache', mock.ANY)
