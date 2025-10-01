"""
Tests for refactored site_functions.py functionality
Tests the new consolidated functions we created during refactoring
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from wo.cli.plugins.site_functions import (
    setup_letsencrypt,
    setup_letsencrypt_advanced,
    determine_site_type,
    handle_site_error_cleanup,
    SiteError
)


class TestSetupLetsencrypt(unittest.TestCase):
    """Test the simple setup_letsencrypt function"""

    def setUp(self):
        self.mock_self = Mock()
        self.mock_self.app.config.has_section.return_value = False

        # Mock the required modules
        self.wo_domain_patcher = patch('wo.cli.plugins.site_functions.WODomain')
        self.wo_acme_patcher = patch('wo.cli.plugins.site_functions.WOAcme')
        self.ssl_patcher = patch('wo.cli.plugins.site_functions.SSL')
        self.wo_service_patcher = patch('wo.cli.plugins.site_functions.WOService')
        self.wo_git_patcher = patch('wo.cli.plugins.site_functions.WOGit')
        self.update_site_info_patcher = patch('wo.cli.plugins.site_functions.updateSiteInfo')
        self.log_patcher = patch('wo.cli.plugins.site_functions.Log')

        self.mock_domain = self.wo_domain_patcher.start()
        self.mock_acme = self.wo_acme_patcher.start()
        self.mock_ssl = self.ssl_patcher.start()
        self.mock_service = self.wo_service_patcher.start()
        self.mock_git = self.wo_git_patcher.start()
        self.mock_update_site = self.update_site_info_patcher.start()
        self.mock_log = self.log_patcher.start()

    def tearDown(self):
        patch.stopall()

    def test_setup_letsencrypt_subdomain(self):
        """Test SSL setup for subdomain"""
        # Setup
        self.mock_domain.getlevel.return_value = ('subdomain', 'example.com')
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        result = setup_letsencrypt(self.mock_self, 'test.example.com', '/var/www/test.example.com')

        # Verify
        self.assertTrue(result)
        self.mock_acme.setupletsencrypt.assert_called_once()
        self.mock_acme.deploycert.assert_called_with(self.mock_self, 'test.example.com')
        self.mock_ssl.httpsredirect.assert_called_once()
        self.mock_ssl.siteurlhttps.assert_called_once()
        self.mock_service.reload_service.assert_called_with(self.mock_self, 'nginx')
        self.mock_update_site.assert_called_with(self.mock_self, 'test.example.com', ssl=True)

    def test_setup_letsencrypt_main_domain(self):
        """Test SSL setup for main domain (includes www)"""
        # Setup
        self.mock_domain.getlevel.return_value = ('', 'example.com')
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        result = setup_letsencrypt(self.mock_self, 'example.com', '/var/www/example.com')

        # Verify - should include both domain and www.domain
        self.assertTrue(result)
        call_args = self.mock_acme.setupletsencrypt.call_args
        domains = call_args[0][1]  # Second argument is the domain list
        self.assertIn('example.com', domains)
        self.assertIn('www.example.com', domains)

    def test_setup_letsencrypt_nginx_reload_fails(self):
        """Test handling when nginx reload fails"""
        # Setup
        self.mock_domain.getlevel.return_value = ('', 'example.com')
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = False

        # Execute
        result = setup_letsencrypt(self.mock_self, 'example.com', '/var/www/example.com')

        # Verify
        self.assertFalse(result)
        self.mock_log.error.assert_called()

    def test_setup_letsencrypt_acme_fails(self):
        """Test handling when ACME setup fails"""
        # Setup
        self.mock_domain.getlevel.return_value = ('', 'example.com')
        self.mock_acme.setupletsencrypt.return_value = False

        # Execute
        result = setup_letsencrypt(self.mock_self, 'example.com', '/var/www/example.com')

        # Verify
        self.assertFalse(result)

    def test_setup_letsencrypt_custom_acme_data(self):
        """Test SSL setup with custom acme data"""
        # Setup
        self.mock_domain.getlevel.return_value = ('', 'example.com')
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        custom_acme_data = {
            'dns': True,
            'acme_dns': 'dns_cloudflare',
            'keylength': 'rsa2048'
        }

        # Execute
        result = setup_letsencrypt(self.mock_self, 'example.com', '/var/www/example.com', custom_acme_data)

        # Verify
        self.assertTrue(result)
        call_args = self.mock_acme.setupletsencrypt.call_args
        acme_data = call_args[0][2]  # Third argument is acme_data
        self.assertEqual(acme_data['dns'], True)
        self.assertEqual(acme_data['acme_dns'], 'dns_cloudflare')


class TestDetermineSiteType(unittest.TestCase):
    """Test the determine_site_type function"""

    def setUp(self):
        self.det_site_par_patcher = patch('wo.cli.plugins.site_functions.detSitePar')
        self.mock_det_site_par = self.det_site_par_patcher.start()

    def tearDown(self):
        patch.stopall()

    def test_determine_site_type_proxy(self):
        """Test proxy site type determination"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=['127.0.0.1:8080'],
            alias=None,
            subsiteof=None
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(stype, 'proxy')
        self.assertEqual(cache, '')
        self.assertEqual(extra_info['host'], '127.0.0.1')
        self.assertEqual(extra_info['port'], '8080')

    def test_determine_site_type_proxy_default_port(self):
        """Test proxy site type with default port"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=['127.0.0.1'],
            alias=None,
            subsiteof=None
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(extra_info['port'], '80')

    def test_determine_site_type_alias(self):
        """Test alias site type determination"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=None,
            alias='main-site.com',
            subsiteof=None
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(stype, 'alias')
        self.assertEqual(cache, '')
        self.assertEqual(extra_info['alias_name'], 'main-site.com')

    def test_determine_site_type_subsite(self):
        """Test subsite type determination"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=None,
            alias=None,
            subsiteof='parent-site.com'
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(stype, 'subsite')
        self.assertEqual(cache, '')
        self.assertEqual(extra_info['subsiteof_name'], 'parent-site.com')

    def test_determine_site_type_html_default(self):
        """Test default HTML site type"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=None,
            alias=None,
            subsiteof=None
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(stype, 'html')
        self.assertEqual(cache, 'basic')
        self.assertEqual(extra_info, {})

    def test_determine_site_type_wordpress(self):
        """Test WordPress site type from detSitePar"""
        # Setup
        self.mock_det_site_par.return_value = ('wp', 'wpfc')
        pargs = SimpleNamespace(
            proxy=None,
            alias=None,
            subsiteof=None
        )

        # Execute
        stype, cache, extra_info = determine_site_type(pargs)

        # Verify
        self.assertEqual(stype, 'wp')
        self.assertEqual(cache, 'wpfc')
        self.assertEqual(extra_info, {})

    def test_determine_site_type_error_handling(self):
        """Test error handling in site type determination"""
        # Setup
        self.mock_det_site_par.side_effect = RuntimeError("Invalid options")
        pargs = SimpleNamespace(proxy=None, alias=None, subsiteof=None)

        # Execute & Verify
        with self.assertRaises(SiteError) as context:
            determine_site_type(pargs)

        self.assertIn("Please provide valid options", str(context.exception))

    def test_determine_site_type_conflicting_options(self):
        """Test conflicting site type options"""
        # Setup
        self.mock_det_site_par.return_value = ('wp', 'basic')
        pargs = SimpleNamespace(
            proxy=['127.0.0.1:8080'],
            alias=None,
            subsiteof=None
        )

        # Execute & Verify
        with self.assertRaises(SiteError) as context:
            determine_site_type(pargs)

        self.assertIn("proxy should not be used with other site types", str(context.exception))

    def test_determine_site_type_empty_proxy_info(self):
        """Test empty proxy information"""
        # Setup
        self.mock_det_site_par.return_value = (None, '')
        pargs = SimpleNamespace(
            proxy=['   '],  # Empty/whitespace proxy info
            alias=None,
            subsiteof=None
        )

        # Execute & Verify
        with self.assertRaises(SiteError) as context:
            determine_site_type(pargs)

        self.assertIn("Please provide proxy server host information", str(context.exception))


class TestHandleSiteErrorCleanup(unittest.TestCase):
    """Test the handle_site_error_cleanup function"""

    def setUp(self):
        self.log_patcher = patch('wo.cli.plugins.site_functions.Log')
        self.do_cleanup_patcher = patch('wo.cli.plugins.site_functions.doCleanupAction')
        self.delete_site_info_patcher = patch('wo.cli.plugins.site_functions.deleteSiteInfo')

        self.mock_log = self.log_patcher.start()
        self.mock_do_cleanup = self.do_cleanup_patcher.start()
        self.mock_delete_site = self.delete_site_info_patcher.start()

        self.mock_self = Mock()

    def tearDown(self):
        patch.stopall()

    def test_handle_site_error_cleanup_basic(self):
        """Test basic error cleanup without database"""
        # Execute
        handle_site_error_cleanup(self.mock_self, 'test.com', '/var/www/test.com')

        # Verify
        self.mock_log.info.assert_any_call(
            self.mock_self,
            self.mock_log.FAIL + "There was a serious error encountered..."
        )
        self.mock_log.info.assert_any_call(
            self.mock_self,
            self.mock_log.FAIL + "Cleaning up afterwards..."
        )
        self.mock_do_cleanup.assert_called_once_with(
            self.mock_self,
            domain='test.com',
            webroot='/var/www/test.com'
        )
        self.mock_delete_site.assert_called_once_with(self.mock_self, 'test.com')
        self.mock_log.error.assert_called_once()

    def test_handle_site_error_cleanup_with_database(self):
        """Test error cleanup with database information"""
        # Execute
        handle_site_error_cleanup(
            self.mock_self,
            'test.com',
            '/var/www/test.com',
            db_name='test_db',
            db_user='test_user',
            db_host='localhost'
        )

        # Verify
        self.assertEqual(self.mock_do_cleanup.call_count, 2)

        # First call for webroot cleanup
        first_call = self.mock_do_cleanup.call_args_list[0]
        self.assertEqual(first_call[1]['domain'], 'test.com')
        self.assertEqual(first_call[1]['webroot'], '/var/www/test.com')

        # Second call for database cleanup
        second_call = self.mock_do_cleanup.call_args_list[1]
        self.assertEqual(second_call[1]['domain'], 'test.com')
        self.assertEqual(second_call[1]['dbname'], 'test_db')
        self.assertEqual(second_call[1]['dbuser'], 'test_user')
        self.assertEqual(second_call[1]['dbhost'], 'localhost')

    def test_handle_site_error_cleanup_partial_database_info(self):
        """Test cleanup with partial database info (should not cleanup db)"""
        # Execute - missing db_host
        handle_site_error_cleanup(
            self.mock_self,
            'test.com',
            '/var/www/test.com',
            db_name='test_db',
            db_user='test_user'
        )

        # Verify - should only do webroot cleanup
        self.mock_do_cleanup.assert_called_once_with(
            self.mock_self,
            domain='test.com',
            webroot='/var/www/test.com'
        )


class TestSetupLetsencryptAdvanced(unittest.TestCase):
    """Test the setup_letsencrypt_advanced function"""

    def setUp(self):
        self.mock_self = Mock()
        self.mock_self.app.config.has_section.return_value = False

        # Mock all the required modules
        self.wo_acme_patcher = patch('wo.cli.plugins.site_functions.WOAcme')
        self.ssl_patcher = patch('wo.cli.plugins.site_functions.SSL')
        self.wo_service_patcher = patch('wo.cli.plugins.site_functions.WOService')
        self.wo_git_patcher = patch('wo.cli.plugins.site_functions.WOGit')
        self.update_site_info_patcher = patch('wo.cli.plugins.site_functions.updateSiteInfo')
        self.log_patcher = patch('wo.cli.plugins.site_functions.Log')

        self.mock_acme = self.wo_acme_patcher.start()
        self.mock_ssl = self.ssl_patcher.start()
        self.mock_service = self.wo_service_patcher.start()
        self.mock_git = self.wo_git_patcher.start()
        self.mock_update_site = self.update_site_info_patcher.start()
        self.mock_log = self.log_patcher.start()

    def tearDown(self):
        patch.stopall()

    def test_setup_letsencrypt_advanced_basic(self):
        """Test basic advanced SSL setup"""
        # Setup
        pargs = SimpleNamespace(
            letsencrypt='on',
            dns=None,
            dnsalias=None,
            force=False,
            hsts=False
        )

        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_acme.check_dns.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        result = setup_letsencrypt_advanced(
            self.mock_self,
            'example.com',
            pargs,
            '',  # domain_type
            'example.com',  # root_domain
            '/var/www/example.com'
        )

        # Verify
        self.assertTrue(result)
        self.mock_acme.setupletsencrypt.assert_called_once()
        self.mock_acme.deploycert.assert_called_with(self.mock_self, 'example.com')
        self.mock_ssl.httpsredirect.assert_called_once()
        self.mock_service.reload_service.assert_called_with(self.mock_self, 'nginx')

    def test_setup_letsencrypt_advanced_wildcard(self):
        """Test wildcard SSL setup"""
        # Setup
        pargs = SimpleNamespace(
            letsencrypt='wildcard',
            dns=None,
            dnsalias=None,
            force=False,
            hsts=False
        )

        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        result = setup_letsencrypt_advanced(
            self.mock_self,
            'example.com',
            pargs,
            '',
            'example.com',
            '/var/www/example.com'
        )

        # Verify wildcard domains are set
        call_args = self.mock_acme.setupletsencrypt.call_args
        acme_domains = call_args[0][1]
        self.assertIn('example.com', acme_domains)
        self.assertIn('*.example.com', acme_domains)

        # Verify DNS is enabled for wildcard
        acme_data = call_args[0][2]
        self.assertTrue(acme_data['dns'])

    def test_setup_letsencrypt_advanced_with_hsts(self):
        """Test SSL setup with HSTS"""
        # Setup
        pargs = SimpleNamespace(
            letsencrypt='on',
            dns=None,
            dnsalias=None,
            force=False,
            hsts=True
        )

        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        setup_letsencrypt_advanced(
            self.mock_self,
            'example.com',
            pargs,
            '',
            'example.com',
            '/var/www/example.com'
        )

        # Verify HSTS setup is called
        self.mock_ssl.setuphsts.assert_called_with(self.mock_self, 'example.com')

    def test_setup_letsencrypt_advanced_dns_validation(self):
        """Test DNS validation setup"""
        # Setup
        pargs = SimpleNamespace(
            letsencrypt='on',
            dns='dns_cloudflare',
            dnsalias=None,
            force=False,
            hsts=False
        )

        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = True

        # Execute
        setup_letsencrypt_advanced(
            self.mock_self,
            'example.com',
            pargs,
            '',
            'example.com',
            '/var/www/example.com'
        )

        # Verify DNS settings
        call_args = self.mock_acme.setupletsencrypt.call_args
        acme_data = call_args[0][2]
        self.assertTrue(acme_data['dns'])
        self.assertEqual(acme_data['acme_dns'], 'dns_cloudflare')

    def test_setup_letsencrypt_advanced_nginx_reload_fails(self):
        """Test handling when nginx reload fails"""
        # Setup
        pargs = SimpleNamespace(
            letsencrypt='on',
            dns=None,
            dnsalias=None,
            force=False,
            hsts=False
        )

        self.mock_acme.cert_check.return_value = False
        self.mock_acme.setupletsencrypt.return_value = True
        self.mock_service.reload_service.return_value = False

        # Execute
        result = setup_letsencrypt_advanced(
            self.mock_self,
            'example.com',
            pargs,
            '',
            'example.com',
            '/var/www/example.com'
        )

        # Verify
        self.assertFalse(result)
        self.mock_log.error.assert_called()


if __name__ == '__main__':
    unittest.main()