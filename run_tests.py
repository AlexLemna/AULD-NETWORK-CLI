#!/usr/bin/env python3
"""
Test runner script for the Auld Network CLI project.

This script runs all tests and provides a summary of results.
You can also run specific test classes or methods.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py TestCommand        # Run specific test class
    python run_tests.py TestCommand.test_command_creation_with_tuple  # Run specific test
"""

import sys
import unittest
from pathlib import Path

# Add the current directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))


def run_tests(test_pattern=None):
    """Run the test suite."""

    # Discover and run tests
    if test_pattern:
        # Run specific test
        suite = unittest.TestLoader().loadTestsFromName(
            test_pattern, module=__import__("test_main")
        )
    else:
        # Run all tests
        suite = unittest.TestLoader().discover(".", pattern="test_*.py")

    # Run the tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print(f"\nFAILURES ({len(result.failures)}):")
        for test, traceback in result.failures:
            print(f"  - {test}")

    if result.errors:
        print(f"\nERRORS ({len(result.errors)}):")
        for test, traceback in result.errors:
            print(f"  - {test}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nResult: {'PASSED' if success else 'FAILED'}")

    return 0 if success else 1


if __name__ == "__main__":
    test_pattern = sys.argv[1] if len(sys.argv) > 1 else None
    exit_code = run_tests(test_pattern)
    sys.exit(exit_code)
