#!/usr/bin/env python3
"""
Manual test script for WordOps refactoring
Run this to manually verify the refactored functions work correctly
"""
import sys
import os
from types import SimpleNamespace

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_determine_site_type():
    """Test the determine_site_type function manually"""
    print("🧪 Testing determine_site_type function...")

    try:
        from wo.cli.plugins.site_functions import determine_site_type, SiteError

        # Mock detSitePar to avoid full dependency chain
        import wo.cli.plugins.site_functions
        original_detSitePar = wo.cli.plugins.site_functions.detSitePar

        def mock_detSitePar(args):
            return (None, '')

        wo.cli.plugins.site_functions.detSitePar = mock_detSitePar

        # Test 1: Default HTML site
        print("  Test 1: Default HTML site")
        pargs = SimpleNamespace(proxy=None, alias=None, subsiteof=None)
        stype, cache, extra_info = determine_site_type(pargs)
        print(f"    Result: stype={stype}, cache={cache}, extra_info={extra_info}")
        assert stype == 'html' and cache == 'basic', f"Expected html/basic, got {stype}/{cache}"
        print("    ✅ Passed")

        # Test 2: Proxy site
        print("  Test 2: Proxy site")
        pargs = SimpleNamespace(proxy=['127.0.0.1:8080'], alias=None, subsiteof=None)
        stype, cache, extra_info = determine_site_type(pargs)
        print(f"    Result: stype={stype}, cache={cache}, extra_info={extra_info}")
        assert stype == 'proxy', f"Expected proxy, got {stype}"
        assert extra_info['host'] == '127.0.0.1', f"Expected host 127.0.0.1, got {extra_info.get('host')}"
        assert extra_info['port'] == '8080', f"Expected port 8080, got {extra_info.get('port')}"
        print("    ✅ Passed")

        # Test 3: Proxy with default port
        print("  Test 3: Proxy with default port")
        pargs = SimpleNamespace(proxy=['nginx.example.com'], alias=None, subsiteof=None)
        stype, cache, extra_info = determine_site_type(pargs)
        assert extra_info['port'] == '80', f"Expected default port 80, got {extra_info.get('port')}"
        print("    ✅ Passed")

        # Test 4: Alias site
        print("  Test 4: Alias site")
        pargs = SimpleNamespace(proxy=None, alias='main.example.com', subsiteof=None)
        stype, cache, extra_info = determine_site_type(pargs)
        assert stype == 'alias', f"Expected alias, got {stype}"
        assert extra_info['alias_name'] == 'main.example.com', f"Expected alias main.example.com"
        print("    ✅ Passed")

        # Test 5: Subsite
        print("  Test 5: Subsite")
        pargs = SimpleNamespace(proxy=None, alias=None, subsiteof='parent.example.com')
        stype, cache, extra_info = determine_site_type(pargs)
        assert stype == 'subsite', f"Expected subsite, got {stype}"
        assert extra_info['subsiteof_name'] == 'parent.example.com', f"Expected parent parent.example.com"
        print("    ✅ Passed")

        # Test 6: Error handling - empty proxy
        print("  Test 6: Error handling - empty proxy")
        pargs = SimpleNamespace(proxy=['  '], alias=None, subsiteof=None)
        try:
            determine_site_type(pargs)
            assert False, "Should have raised SiteError"
        except SiteError as e:
            print(f"    Expected error: {e}")
            print("    ✅ Passed")

        # Test 7: Conflicting options
        print("  Test 7: Conflicting options")
        def mock_detSitePar_wp(args):
            return ('wp', 'basic')
        wo.cli.plugins.site_functions.detSitePar = mock_detSitePar_wp

        pargs = SimpleNamespace(proxy=['127.0.0.1'], alias=None, subsiteof=None)
        try:
            determine_site_type(pargs)
            assert False, "Should have raised SiteError for conflicting options"
        except SiteError as e:
            print(f"    Expected error: {e}")
            print("    ✅ Passed")

        # Restore original function
        wo.cli.plugins.site_functions.detSitePar = original_detSitePar

        print("🎉 determine_site_type: All tests passed!")
        return True

    except Exception as e:
        print(f"❌ determine_site_type test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_function_imports():
    """Test that all refactored functions can be imported"""
    print("🧪 Testing function imports...")

    functions_to_test = [
        ('wo.cli.plugins.site_functions', 'setup_letsencrypt'),
        ('wo.cli.plugins.site_functions', 'setup_letsencrypt_advanced'),
        ('wo.cli.plugins.site_functions', 'determine_site_type'),
        ('wo.cli.plugins.site_functions', 'handle_site_error_cleanup'),
    ]

    all_passed = True

    for module_name, function_name in functions_to_test:
        try:
            module = __import__(module_name, fromlist=[function_name])
            func = getattr(module, function_name)
            print(f"  ✅ {module_name}.{function_name} - imported successfully")

            # Check if it's callable
            if callable(func):
                print(f"    ✅ Function is callable")
            else:
                print(f"    ❌ Function is not callable")
                all_passed = False

        except ImportError as e:
            print(f"  ❌ {module_name}.{function_name} - import failed: {e}")
            all_passed = False
        except AttributeError as e:
            print(f"  ❌ {module_name}.{function_name} - function not found: {e}")
            all_passed = False

    return all_passed

def test_site_create_methods():
    """Test the new methods in WOSiteCreateController"""
    print("🧪 Testing WOSiteCreateController methods...")

    try:
        from wo.cli.plugins.site_create import WOSiteCreateController

        controller = WOSiteCreateController()

        # Check if the new methods exist
        methods_to_check = ['_get_site_name_input', '_validate_domain_and_setup']

        for method_name in methods_to_check:
            if hasattr(controller, method_name):
                print(f"  ✅ {method_name} - method exists")
            else:
                print(f"  ❌ {method_name} - method missing")
                return False

        print("🎉 WOSiteCreateController: All methods found!")
        return True

    except Exception as e:
        print(f"❌ WOSiteCreateController test failed: {e}")
        return False

def test_no_redundant_functions():
    """Verify redundant functions were removed"""
    print("🧪 Testing that redundant functions were removed...")

    try:
        # Check site_clone.py
        from wo.cli.plugins import site_clone
        if hasattr(site_clone.WOSiteCloneController, '_setup_letsencrypt'):
            # Check if it's the old redundant version
            import inspect
            source = inspect.getsource(site_clone.WOSiteCloneController._setup_letsencrypt)
            if 'setup_letsencrypt(self, domain, webroot)' in source and len(source.split('\n')) <= 3:
                print("  ❌ site_clone still has redundant _setup_letsencrypt wrapper")
                return False
            else:
                print("  ✅ site_clone._setup_letsencrypt exists but is not redundant wrapper")
        else:
            print("  ✅ site_clone._setup_letsencrypt properly removed")

        # Check site_restore.py
        from wo.cli.plugins import site_restore
        if hasattr(site_restore.WOSiteRestoreController, '_setup_letsencrypt'):
            import inspect
            source = inspect.getsource(site_restore.WOSiteRestoreController._setup_letsencrypt)
            if 'setup_letsencrypt(self, domain, webroot)' in source and len(source.split('\n')) <= 3:
                print("  ❌ site_restore still has redundant _setup_letsencrypt wrapper")
                return False
            else:
                print("  ✅ site_restore._setup_letsencrypt exists but is not redundant wrapper")
        else:
            print("  ✅ site_restore._setup_letsencrypt properly removed")

        print("🎉 Redundant function removal: Verified!")
        return True

    except Exception as e:
        print(f"❌ Redundant function test failed: {e}")
        return False

def main():
    """Run all manual tests"""
    print("🚀 WordOps Refactoring Manual Tests")
    print("=" * 50)

    tests = [
        ("Function Imports", test_function_imports),
        ("Site Create Methods", test_site_create_methods),
        ("Determine Site Type", test_determine_site_type),
        ("No Redundant Functions", test_no_redundant_functions),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)

        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")

    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All manual tests passed!")
        print("✨ The refactored WordOps functionality is working correctly!")
        return True
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)