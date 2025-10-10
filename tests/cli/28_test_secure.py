from unittest import TestCase, mock
import importlib

from wo.cli.main import WOTestApp


class CliTestCaseSecure(TestCase):

    def test_secure_domain_renders_protected(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            site_secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.site_secure'))
            site_mod = importlib.reload(importlib.import_module('wo.cli.plugins.site'))
            fake_site_funcs.getSiteInfo.return_value = mock.Mock(
                site_path='/var/www/example.com',
                site_type='wp',
                php_version='8.1',
            )
            with mock.patch.object(site_secure_mod.os, 'makedirs'), \
                 mock.patch.object(site_secure_mod.WOTemplate, 'deploy') as mock_deploy, \
                 mock.patch.object(site_secure_mod.WOGit, 'add') as mock_git_add, \
                 mock.patch.object(site_secure_mod.WOService, 'reload_service', return_value=True), \
                 mock.patch.object(site_secure_mod.WOShellExec, 'cmd_exec_stdout', return_value='hashed\n') as mock_cmd_exec, \
                 mock.patch('builtins.open', mock.mock_open()) as mock_file:
                with WOTestApp(argv=['site', 'secure', 'example.com', 'user', 'pass']) as app:
                    site_mod.load(app)
                    app.run()

                expected_data = {
                    'slug': 'example-com',
                    'secure': True,
                    'wp': True,
                    'php_ver': '81',
                    'pool_name': 'example-com',
                }
                mock_deploy.assert_called_with(mock.ANY, '/etc/nginx/acl/example-com/protected.conf', 'protected.mustache', expected_data, overwrite=True)
                mock_cmd_exec.assert_called_with(mock.ANY, ['openssl', 'passwd', '-apr1', 'pass'], errormsg='Failed to generate HTTP authentication hash.', log=False)
                mock_file.assert_called_with('/etc/nginx/acl/example-com/credentials', 'w', encoding='utf-8')
                mock_file().write.assert_called_with('user:hashed\n')
                mock_git_add.assert_called_with(mock.ANY, ['/etc/nginx'], msg='Secured example.com with basic auth')

    def test_clear_acl_removes_credentials_and_rerenders(self):
        fake_site_funcs = mock.Mock()
        fake_site_funcs.getSiteInfo = mock.Mock()
        with mock.patch.dict('sys.modules', {
            'apt': mock.Mock(),
            'wo.cli.plugins.site_functions': fake_site_funcs,
        }):
            site_secure_mod = importlib.reload(importlib.import_module('wo.cli.plugins.site_secure'))
            site_mod = importlib.reload(importlib.import_module('wo.cli.plugins.site'))
            credentials = '/etc/nginx/acl/example-com/credentials'
            fake_site_funcs.getSiteInfo.return_value = mock.Mock(
                site_path='/var/www/example.com',
                site_type='html',
                php_version='8.1',
            )
            with mock.patch.object(site_secure_mod.os.path, 'exists', return_value=True), \
                 mock.patch.object(site_secure_mod.os, 'remove') as mock_remove, \
                 mock.patch.object(site_secure_mod.WOTemplate, 'deploy') as mock_deploy, \
                 mock.patch.object(site_secure_mod.WOGit, 'add') as mock_git_add, \
                 mock.patch.object(site_secure_mod.WOService, 'reload_service', return_value=True):
                with WOTestApp(argv=['site', 'secure', '--rm', 'example.com']) as app:
                    site_mod.load(app)
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

    def test_secure_ssh_long_flags_are_supported(self):
        secure_ssh_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure_ssh'))

        with mock.patch.object(secure_ssh_mod.WOSecureController, '_prompt_password', return_value='secret'), \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_set_hostname') as mock_set_hostname, \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_ensure_hosts_entry') as mock_hosts_entry, \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_provision_user') as mock_provision_user, \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_render_sshd_config') as mock_render_config, \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_read_current_port', return_value='22'):
            with WOTestApp(argv=['secure', 'ssh', '--hostname', 'example.com', '--user', 'admin', '--port', '2222', '--allow-password', '--force']) as app:
                secure_ssh_mod.load(app)
                app.run()

        # Validate hostname configuration sequence
        self.assertEqual(mock_set_hostname.call_count, 1)
        self.assertEqual(mock_set_hostname.call_args[0][1], 'example.com')

        # Ensure hosts entry and user provisioning triggered
        self.assertEqual(mock_hosts_entry.call_count, 1)
        self.assertEqual(mock_hosts_entry.call_args[0][1], 'example.com')
        self.assertEqual(mock_provision_user.call_count, 1)
        self.assertEqual(mock_provision_user.call_args[0][1:], ('admin', 'secret'))

        # SSH config should be rendered with expected values and allow_password=True
        self.assertEqual(mock_render_config.call_count, 1)
        _, username, port, allow_password = mock_render_config.call_args[0]
        self.assertEqual(username, 'admin')
        self.assertEqual(port, '2222')
        self.assertTrue(allow_password)

    def test_secure_ssh_argument_reorder_allows_options_after_command(self):
        secure_ssh_mod = importlib.reload(importlib.import_module('wo.cli.plugins.secure_ssh'))

        with mock.patch.object(secure_ssh_mod.WOSecureController, '_prompt_password', return_value='secret'), \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_set_hostname') as mock_set_hostname, \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_ensure_hosts_entry'), \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_provision_user'), \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_render_sshd_config'), \
             mock.patch.object(secure_ssh_mod.WOSecureController, '_read_current_port', return_value='22'):
            with WOTestApp(argv=['secure', 'ssh', '--hostname', 'example.com', '--user', 'admin', '--port', '2222', '--force']) as app:
                secure_ssh_mod.load(app)
                app.run()

        self.assertEqual(mock_set_hostname.call_args[0][1], 'example.com')
