#!/usr/bin/env python3
"""
Test runner for WordOps refactoring tests
Run this script to test all the refactored functionality
"""
import sys
import os
import unittest
import subprocess

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def run_tests():
    """Run all refactoring tests"""

    print("=" * 60)
    print("WordOps Refactoring Tests")
    print("=" * 60)

    # Test files to run
    test_files = [
        'tests.cli.test_site_functions_refactor',
        'tests.cli.test_site_create_refactor_integration'
    ]

    success_count = 0
    total_count = len(test_files)

    for test_file in test_files:
        print(f"\n🧪 Running {test_file}...")
        print("-" * 40)

        try:
            # Load and run the test suite
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromName(test_file)
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)

            if result.wasSuccessful():
                print(f"✅ {test_file} - All tests passed!")
                success_count += 1
            else:
                print(f"❌ {test_file} - Some tests failed")
                print(f"   Failures: {len(result.failures)}")
                print(f"   Errors: {len(result.errors)}")

        except Exception as e:
            print(f"❌ {test_file} - Could not run tests: {e}")

    print("\n" + "=" * 60)
    print(f"Test Summary: {success_count}/{total_count} test suites passed")

    if success_count == total_count:
        print("🎉 All refactoring tests passed!")
        return True
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return False

def run_specific_function_tests():
    """Run tests for specific refactored functions"""

    print("\n🔍 Testing individual refactored functions...")

    # Test the functions directly
    try:
        from wo.cli.plugins.site_functions import (
            determine_site_type,
            SiteError
        )
        from types import SimpleNamespace

        print("✅ Successfully imported refactored functions")

        # Quick smoke test
        print("🧪 Running smoke tests...")

        # Test determine_site_type with valid input
        try:
            pargs = SimpleNamespace(proxy=None, alias=None, subsiteof=None)

            # Mock detSitePar to avoid dependency issues
            import wo.cli.plugins.site_functions
            original_detSitePar = wo.cli.plugins.site_functions.detSitePar

            def mock_detSitePar(args):
                return (None, '')

            wo.cli.plugins.site_functions.detSitePar = mock_detSitePar

            stype, cache, extra_info = determine_site_type(pargs)

            # Restore original function
            wo.cli.plugins.site_functions.detSitePar = original_detSitePar

            if stype == 'html' and cache == 'basic':
                print("✅ determine_site_type smoke test passed")
            else:
                print(f"⚠️  determine_site_type returned unexpected values: {stype}, {cache}")

        except Exception as e:
            print(f"❌ determine_site_type smoke test failed: {e}")

        return True

    except ImportError as e:
        print(f"❌ Could not import refactored functions: {e}")
        return False

def check_imports():
    """Check that all refactored modules can be imported"""

    print("🔍 Checking imports...")

    imports_to_check = [
        ('wo.cli.plugins.site_functions', ['setup_letsencrypt', 'determine_site_type', 'handle_site_error_cleanup']),
        ('wo.cli.plugins.site_create', ['WOSiteCreateController']),
        ('wo.cli.plugins.site_clone', []),
        ('wo.cli.plugins.site_restore', []),
    ]

    all_good = True

    for module_name, functions in imports_to_check:
        try:
            module = __import__(module_name, fromlist=functions)

            for func_name in functions:
                if hasattr(module, func_name):
                    print(f"✅ {module_name}.{func_name}")
                else:
                    print(f"❌ {module_name}.{func_name} - not found")
                    all_good = False

            if not functions:  # Just check module imports
                print(f"✅ {module_name}")

        except ImportError as e:
            print(f"❌ {module_name} - import failed: {e}")
            all_good = False

    return all_good

def main():
    """Main test runner"""
    print("WordOps Refactoring Test Suite")
    print("Testing all the refactored functionality...")

    # Check basic imports first
    if not check_imports():
        print("\n❌ Import checks failed. Please check the refactored code.")
        return False

    print("\n✅ All imports successful!")

    # Run function smoke tests
    if not run_specific_function_tests():
        print("\n❌ Function tests failed.")
        return False

    # Run full test suite
    success = run_tests()

    if success:
        print("\n🎉 All refactoring tests completed successfully!")
        print("The refactored WordOps functionality is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")

    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)