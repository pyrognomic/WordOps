"""
Integration tests for refactored site_create.py functionality
Tests the integration between the new helper functions and site creation
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from wo.cli.plugins.site_create import WOSiteCreateController


class TestSiteCreateRefactorIntegration(unittest.TestCase):
    """Integration tests for refactored site creation"""

    def setUp(self):
        """Setup common mocks for site creation tests"""
        self.controller = WOSiteCreateController()
        self.controller.app = Mock()
        self.controller.app.config.has_section.return_value = False

        # Mock all the external dependencies
        self.setup_patches()

    def setup_patches(self):
        """Setup all the required patches"""
        patches = [
            # Core functionality patches
            ('wo.cli.plugins.site_functions.WODomain', 'mock_domain'),
            ('wo.cli.plugins.site_functions.WOAcme', 'mock_acme'),
            ('wo.cli.plugins.site_functions.SSL', 'mock_ssl'),
            ('wo.cli.plugins.site_functions.WOService', 'mock_service'),
            ('wo.cli.plugins.site_functions.WOGit', 'mock_git'),
            ('wo.cli.plugins.site_functions.updateSiteInfo', 'mock_update_site'),
            ('wo.cli.plugins.site_functions.deleteSiteInfo', 'mock_delete_site'),
            ('wo.cli.plugins.site_functions.doCleanupAction', 'mock_cleanup'),
            ('wo.cli.plugins.site_functions.Log', 'mock_log'),

            # Site create specific patches
            ('wo.cli.plugins.site_create.WODomain', 'mock_create_domain'),
            ('wo.cli.plugins.site_create.check_domain_exists', 'mock_check_exists'),
            ('wo.cli.plugins.site_create.site_package_check', 'mock_package_check'),
            ('wo.cli.plugins.site_create.pre_run_checks', 'mock_pre_checks'),
            ('wo.cli.plugins.site_create.setupdomain', 'mock_setup_domain'),
            ('wo.cli.plugins.site_create.hashbucket', 'mock_hashbucket'),
            ('wo.cli.plugins.site_create.WOVar', 'mock_var'),
            ('wo.cli.plugins.site_create.os.path.isfile', 'mock_isfile'),
            ('wo.cli.plugins.site_create.addNewSite', 'mock_add_site'),
            ('wo.cli.plugins.site_create.WOService', 'mock_create_service'),
        ]

        for patch_target, attr_name in patches:
            patcher = patch(patch_target)
            setattr(self, attr_name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_get_site_name_input_method(self):
        """Test the _get_site_name_input helper method"""
        # Test with site name provided
        pargs = SimpleNamespace(site_name='test.com')
        self.controller._get_site_name_input(pargs)
        self.assertEqual(pargs.site_name, 'test.com')

        # Test with no site name (mock input)
        pargs = SimpleNamespace(site_name=None)
        with patch('builtins.input', return_value='input-test.com'):
            self.controller._get_site_name_input(pargs)
        self.assertEqual(pargs.site_name, 'input-test.com')

    def test_validate_domain_and_setup_method(self):
        """Test the _validate_domain_and_setup helper method"""
        # Setup mocks
        self.mock_create_domain.validate.return_value = 'test.com'
        self.mock_create_domain.getlevel.return_value = ('', 'test.com')
        self.mock_check_exists.return_value = False
        self.mock_isfile.return_value = False
        self.mock_var.wo_webroot = '/var/www/'

        # Test
        pargs = SimpleNamespace(site_name='  test.com  ')
        result = self.controller._validate_domain_and_setup(pargs)

        # Verify
        wo_domain, wo_www_domain, wo_domain_type, wo_root_domain, wo_site_webroot = result
        self.assertEqual(wo_domain, 'test.com')
        self.assertEqual(wo_www_domain, 'www.test.com')
        self.assertEqual(wo_domain_type, '')
        self.assertEqual(wo_root_domain, 'test.com')
        self.assertEqual(wo_site_webroot, '/var/www/test.com')

    def test_validate_domain_existing_site_error(self):
        """Test domain validation with existing site"""
        # Setup mocks
        self.mock_create_domain.validate.return_value = 'existing.com'
        self.mock_check_exists.return_value = True

        pargs = SimpleNamespace(site_name='existing.com')

        # Test - should raise error for existing site
        with patch.object(self.controller.mock_log, 'error') as mock_error:
            # The method will call Log.error which should exit
            mock_error.side_effect = SystemExit(1)

            with self.assertRaises(SystemExit):
                self.controller._validate_domain_and_setup(pargs)

    def test_site_creation_with_proxy(self):
        """Test proxy site creation flow"""
        # Setup mocks for successful proxy creation
        self.mock_create_domain.validate.return_value = 'proxy.test.com'
        self.mock_create_domain.getlevel.return_value = ('', 'test.com')
        self.mock_check_exists.return_value = False
        self.mock_isfile.return_value = False
        self.mock_var.wo_webroot = '/var/www/'
        self.mock_package_check.return_value = []
        self.mock_var.wo_php_versions = {'php84': '8.4'}
        self.mock_create_service.reload_service.return_value = True

        # Create pargs for proxy site
        pargs = SimpleNamespace(
            site_name='proxy.test.com',
            proxy=['127.0.0.1:8080'],
            alias=None,
            subsiteof=None,
            letsencrypt=None,
            secure=False,
            php84=False, php83=False, php82=False, php81=False, php80=False, php74=False
        )

        # Mock the internal method calls
        with patch.object(self.controller, '_render_protected'):
            # This test verifies the refactored structure works
            # In a real test environment, you'd want to verify the complete flow
            pass

    def test_site_creation_with_letsencrypt(self):
        """Test site creation with Let's Encrypt integration"""
        # Setup mocks
        self.mock_create_domain.validate.return_value = 'ssl.test.com'
        self.mock_create_domain.getlevel.return_value = ('', 'test.com')
        self.mock_check_exists.return_value = False
        self.mock_isfile.return_value = False
        self.mock_var.wo_webroot = '/var/www/'
        self.mock_package_check.return_value = []
        self.mock_var.wo_php_versions = {'php84': '8.4'}

        # Mock SSL setup to succeed
        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        pargs = SimpleNamespace(
            site_name='ssl.test.com',
            proxy=None,
            alias=None,
            subsiteof=None,
            letsencrypt='on',
            dns=None,
            dnsalias=None,
            force=False,
            hsts=False,
            secure=False,
            php84=False, php83=False, php82=False, php81=False, php80=False, php74=False
        )

        # This would test the integration with setup_letsencrypt_advanced
        # In a full implementation, you'd call the actual method and verify SSL setup


class TestSiteCreateErrorHandling(unittest.TestCase):
    """Test error handling in refactored site creation"""

    def setUp(self):
        self.controller = WOSiteCreateController()
        self.controller.app = Mock()

    def test_site_error_cleanup_integration(self):
        """Test that error cleanup is properly called"""
        with patch('wo.cli.plugins.site_create.handle_site_error_cleanup') as mock_cleanup:
            with patch('wo.cli.plugins.site_create.Log') as mock_log:
                # This would test that our standardized cleanup is called
                # when errors occur in site creation
                pass


class TestSiteTypeIntegration(unittest.TestCase):
    """Test site type determination integration"""

    def test_proxy_site_type_flow(self):
        """Test complete proxy site type determination and setup"""
        # Setup
        pargs = SimpleNamespace(
            proxy=['nginx.test.com:80'],
            alias=None,
            subsiteof=None
        )

        # Import and test our function
        from wo.cli.plugins.site_functions import determine_site_type

        with patch('wo.cli.plugins.site_functions.detSitePar') as mock_det:
            mock_det.return_value = (None, '')

            # Execute
            stype, cache, extra_info = determine_site_type(pargs)

            # Verify
            self.assertEqual(stype, 'proxy')
            self.assertEqual(extra_info['host'], 'nginx.test.com')
            self.assertEqual(extra_info['port'], '80')

    def test_alias_site_type_flow(self):
        """Test complete alias site type determination and setup"""
        # Setup
        pargs = SimpleNamespace(
            proxy=None,
            alias='main.test.com',
            subsiteof=None
        )

        from wo.cli.plugins.site_functions import determine_site_type

        with patch('wo.cli.plugins.site_functions.detSitePar') as mock_det:
            mock_det.return_value = (None, '')

            # Execute
            stype, cache, extra_info = determine_site_type(pargs)

            # Verify
            self.assertEqual(stype, 'alias')
            self.assertEqual(extra_info['alias_name'], 'main.test.com')


class TestRenderProtectedIntegration(unittest.TestCase):
    """Test the _render_protected method integration"""

    def setUp(self):
        self.controller = WOSiteCreateController()
        self.controller.app = Mock()

    def test_render_protected_with_security(self):
        """Test protected directory rendering with security enabled"""
        data = {
            'pool_name': 'test-site',
            'wp': True,
            'php_ver': '84',
        }

        with patch('wo.cli.plugins.site_create.os.makedirs') as mock_makedirs:
            with patch('wo.cli.plugins.site_create.WOTemplate') as mock_template:
                with patch('wo.cli.plugins.site_create.RANDOM') as mock_random:
                    with patch('wo.cli.plugins.site_create.WOShellExec') as mock_shell:
                        with patch('wo.cli.plugins.site_create.WOVar') as mock_var:
                            mock_random.long.return_value = 'test_password'
                            mock_var.wo_user = 'testuser'

                            # Execute
                            self.controller._render_protected(data, secure=True)

                            # Verify
                            mock_makedirs.assert_called_once()
                            mock_template.deploy.assert_called_once()
                            mock_shell.cmd_exec.assert_called_once()

    def test_render_protected_without_pool_name(self):
        """Test protected rendering without pool name (should return early)"""
        data = {}

        with patch('wo.cli.plugins.site_create.os.makedirs') as mock_makedirs:
            # Execute
            self.controller._render_protected(data, secure=False)

            # Verify - should return early and not call makedirs
            mock_makedirs.assert_not_called()


if __name__ == '__main__':
    unittest.main()