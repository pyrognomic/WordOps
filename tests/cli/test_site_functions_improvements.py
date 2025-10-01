"""
Tests for improved site_functions.py functionality
Tests the new consolidated and refactored functions
"""
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import sys
import os
import string

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from wo.cli.plugins.site_functions import (
    detSitePar,
    generate_random,
    generate_random_pass,
    generate_8_random,
    PHPVersionManager,
    SiteError
)


class TestDetSiteParRefactored(unittest.TestCase):
    """Test the refactored detSitePar function - reduced from 270 lines to ~90 lines"""

    def test_single_type_html(self):
        """Test single HTML type"""
        opts = {'html': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('html', 'basic'))

    def test_single_type_php(self):
        """Test single PHP type"""
        opts = {'php': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('php', 'basic'))

    def test_single_type_wp(self):
        """Test single WordPress type"""
        opts = {'wp': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wp', 'basic'))

    def test_single_php_version(self):
        """Test single PHP version"""
        opts = {'php84': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('php84', 'basic'))

    def test_no_type_with_cache(self):
        """Test no type but cache specified defaults to WordPress"""
        opts = {'wpfc': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wp', 'wpfc'))

    def test_php_version_with_cache(self):
        """Test PHP version with cache defaults to WordPress"""
        opts = {'php84': True, 'wpredis': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wp', 'wpredis'))

    def test_mysql_combination_classic(self):
        """Test classic MySQL combination (php + mysql + html)"""
        opts = {'php': True, 'mysql': True, 'html': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('mysql', 'basic'))

    def test_mysql_combination_with_php_version(self):
        """Test MySQL combination with PHP version (php84 + mysql + html)"""
        opts = {'php84': True, 'mysql': True, 'html': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('mysql', 'basic'))

    def test_mysql_combination_with_cache(self):
        """Test MySQL combination with cache"""
        opts = {'php': True, 'mysql': True, 'wpfc': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('mysql', 'wpfc'))

    def test_wordpress_multisite_subdirectory(self):
        """Test WordPress multisite subdirectory"""
        opts = {'wp': True, 'wpsubdir': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wpsubdir', 'basic'))

    def test_wordpress_multisite_subdomain(self):
        """Test WordPress multisite subdomain"""
        opts = {'wp': True, 'wpsubdomain': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wpsubdomain', 'basic'))

    def test_wordpress_with_php_version(self):
        """Test WordPress with specific PHP version"""
        opts = {'wp': True, 'php83': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wp', 'basic'))

    def test_wpsubdir_with_php_version(self):
        """Test WordPress subdirectory with PHP version"""
        opts = {'wpsubdir': True, 'php82': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wpsubdir', 'basic'))

    def test_wpsubdomain_with_php_version(self):
        """Test WordPress subdomain with PHP version"""
        opts = {'wpsubdomain': True, 'php81': True}
        result = detSitePar(opts)
        self.assertEqual(result, ('wpsubdomain', 'basic'))

    def test_multiple_cache_error(self):
        """Test error when multiple cache types specified"""
        opts = {'wp': True, 'wpfc': True, 'wpredis': True}
        with self.assertRaises(RuntimeError) as context:
            detSitePar(opts)
        self.assertIn("Multiple cache parameter entered", str(context.exception))

    def test_invalid_combination_error(self):
        """Test error for invalid type combinations"""
        opts = {'html': True, 'wp': True, 'proxy': True}  # Invalid combination
        with self.assertRaises(RuntimeError) as context:
            detSitePar(opts)
        self.assertIn("could not determine site and cache type", str(context.exception))

    def test_empty_options(self):
        """Test empty options"""
        opts = {}
        result = detSitePar(opts)
        self.assertEqual(result, (None, None))

    def test_all_php_versions_supported(self):
        """Test that all PHP versions are properly handled"""
        php_versions = ['php74', 'php80', 'php81', 'php82', 'php83', 'php84']

        for php_ver in php_versions:
            with self.subTest(php_version=php_ver):
                opts = {php_ver: True}
                result = detSitePar(opts)
                self.assertEqual(result, (php_ver, 'basic'))

                # Test with cache
                opts = {php_ver: True, 'wpfc': True}
                result = detSitePar(opts)
                self.assertEqual(result, ('wp', 'wpfc'))

                # Test with MySQL
                opts = {php_ver: True, 'mysql': True}
                result = detSitePar(opts)
                self.assertEqual(result, ('mysql', 'basic'))


class TestGenerateRandomRefactored(unittest.TestCase):
    """Test the consolidated random generation functions"""

    def test_generate_random_default(self):
        """Test default random generation (24 characters)"""
        result = generate_random()
        self.assertEqual(len(result), 24)
        self.assertTrue(all(c in string.ascii_letters + string.digits for c in result))

    def test_generate_random_custom_length(self):
        """Test custom length random generation"""
        for length in [4, 8, 16, 32]:
            with self.subTest(length=length):
                result = generate_random(length)
                self.assertEqual(len(result), length)

    def test_generate_random_custom_charset(self):
        """Test custom character set"""
        charset = "ABCD1234"
        result = generate_random(8, charset)
        self.assertEqual(len(result), 8)
        self.assertTrue(all(c in charset for c in result))

    def test_generate_random_too_long(self):
        """Test requesting more characters than available in charset"""
        charset = "ABC"
        result = generate_random(10, charset)
        self.assertEqual(len(result), 3)  # Should be limited to charset length

    def test_generate_random_pass_compatibility(self):
        """Test backward compatibility wrapper for password generation"""
        result = generate_random_pass()
        self.assertEqual(len(result), 24)
        self.assertTrue(all(c in string.ascii_letters + string.digits for c in result))

    def test_generate_8_random_compatibility(self):
        """Test backward compatibility wrapper for 8-character generation"""
        result = generate_8_random()
        self.assertEqual(len(result), 8)
        self.assertTrue(all(c in string.ascii_letters + string.digits for c in result))

    def test_random_uniqueness(self):
        """Test that generated strings are reasonably unique"""
        results = set()
        for _ in range(100):
            result = generate_random(16)
            self.assertNotIn(result, results, "Generated duplicate random string")
            results.add(result)


class TestPHPVersionManager(unittest.TestCase):
    """Test the centralized PHP version management"""

    def test_supported_versions(self):
        """Test supported versions list"""
        expected = ['php74', 'php80', 'php81', 'php82', 'php83', 'php84']
        self.assertEqual(PHPVersionManager.SUPPORTED_VERSIONS, expected)

    def test_version_mapping(self):
        """Test version number mapping"""
        self.assertEqual(PHPVersionManager.get_version_number('php74'), '7.4')
        self.assertEqual(PHPVersionManager.get_version_number('php80'), '8.0')
        self.assertEqual(PHPVersionManager.get_version_number('php84'), '8.4')
        self.assertIsNone(PHPVersionManager.get_version_number('invalid'))

    def test_is_php_version(self):
        """Test PHP version detection"""
        self.assertTrue(PHPVersionManager.is_php_version('php74'))
        self.assertTrue(PHPVersionManager.is_php_version('php84'))
        self.assertFalse(PHPVersionManager.is_php_version('php'))
        self.assertFalse(PHPVersionManager.is_php_version('html'))
        self.assertFalse(PHPVersionManager.is_php_version('wp'))

    def test_get_selected_versions_single(self):
        """Test getting single selected PHP version"""
        pargs = SimpleNamespace(php74=False, php80=False, php81=False,
                               php82=False, php83=False, php84=True)
        selected = PHPVersionManager.get_selected_versions(pargs)
        self.assertEqual(selected, ['php84'])

    def test_get_selected_versions_none(self):
        """Test getting selected PHP versions when none selected"""
        pargs = SimpleNamespace(php74=False, php80=False, php81=False,
                               php82=False, php83=False, php84=False)
        selected = PHPVersionManager.get_selected_versions(pargs)
        self.assertEqual(selected, [])

    def test_get_selected_versions_multiple(self):
        """Test getting multiple selected PHP versions"""
        pargs = SimpleNamespace(php74=False, php80=True, php81=False,
                               php82=False, php83=True, php84=False)
        selected = PHPVersionManager.get_selected_versions(pargs)
        self.assertEqual(set(selected), {'php80', 'php83'})

    def test_validate_single_version_success(self):
        """Test successful single version validation"""
        pargs = SimpleNamespace(php74=False, php80=False, php81=False,
                               php82=False, php83=True, php84=False)
        result = PHPVersionManager.validate_single_version(pargs)
        self.assertEqual(result, 'php83')

    def test_validate_single_version_none(self):
        """Test validation with no PHP versions"""
        pargs = SimpleNamespace(php74=False, php80=False, php81=False,
                               php82=False, php83=False, php84=False)
        result = PHPVersionManager.validate_single_version(pargs)
        self.assertIsNone(result)

    def test_validate_single_version_error(self):
        """Test validation error with multiple PHP versions"""
        pargs = SimpleNamespace(php74=True, php80=False, php81=True,
                               php82=False, php83=False, php84=True)
        with self.assertRaises(SiteError) as context:
            PHPVersionManager.validate_single_version(pargs)

        error_msg = str(context.exception.message)
        self.assertIn("Cannot combine multiple PHP versions", error_msg)
        self.assertIn("php74", error_msg)
        self.assertIn("php81", error_msg)
        self.assertIn("php84", error_msg)

    def test_has_any_php_version_true(self):
        """Test detection of any PHP version present"""
        pargs = SimpleNamespace(php74=False, php80=True, php81=False,
                               php82=False, php83=False, php84=False)
        self.assertTrue(PHPVersionManager.has_any_php_version(pargs))

    def test_has_any_php_version_false(self):
        """Test detection of no PHP versions present"""
        pargs = SimpleNamespace(php74=False, php80=False, php81=False,
                               php82=False, php83=False, php84=False)
        self.assertFalse(PHPVersionManager.has_any_php_version(pargs))

    def test_missing_attributes_handled(self):
        """Test handling of missing PHP version attributes"""
        pargs = SimpleNamespace(php74=True)  # Only has php74, missing others
        selected = PHPVersionManager.get_selected_versions(pargs)
        self.assertEqual(selected, ['php74'])


class TestRefactoringBenefits(unittest.TestCase):
    """Tests to demonstrate the benefits of the refactoring"""

    def test_adding_new_php_version_easy(self):
        """Test that adding a new PHP version is now easy"""
        # Before: would need to add 20+ lines across multiple elif statements
        # After: just add to PHPVersionManager.SUPPORTED_VERSIONS

        # Simulate adding php85 (this would work if added to SUPPORTED_VERSIONS)
        old_versions = PHPVersionManager.SUPPORTED_VERSIONS.copy()
        try:
            # Temporarily add php85 to test extensibility
            PHPVersionManager.SUPPORTED_VERSIONS.append('php85')
            PHPVersionManager.VERSION_MAP['php85'] = '8.5'

            # Test that it works immediately in all combinations
            opts = {'php85': True, 'mysql': True}
            result = detSitePar(opts)
            self.assertEqual(result, ('mysql', 'basic'))

            opts = {'wp': True, 'php85': True}
            result = detSitePar(opts)
            self.assertEqual(result, ('wp', 'basic'))

        finally:
            # Restore original versions
            PHPVersionManager.SUPPORTED_VERSIONS[:] = old_versions
            if 'php85' in PHPVersionManager.VERSION_MAP:
                del PHPVersionManager.VERSION_MAP['php85']

    def test_code_maintainability_improved(self):
        """Test that the refactored code is more maintainable"""
        # Before: 270 lines with massive duplication
        # After: ~90 lines with clear, testable functions

        # Test complex combinations that were previously buried in huge if-elif chains
        combinations = [
            ({'wp': True, 'php74': True, 'wpredis': True}, ('wp', 'wpredis')),
            ({'wpsubdir': True, 'php80': True, 'wpfc': True}, ('wpsubdir', 'wpfc')),
            ({'php81': True, 'mysql': True, 'html': True, 'wprocket': True}, ('mysql', 'wprocket')),
            ({'php82': True, 'mysql': True, 'wpsc': True}, ('mysql', 'wpsc')),
        ]

        for opts, expected in combinations:
            with self.subTest(opts=opts):
                result = detSitePar(opts)
                self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()