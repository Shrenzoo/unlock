"""Fixtures and reporting hooks for the browser suite live in browser_harness."""

from browser_harness import (  # noqa: F401  (re-exported for pytest discovery)
    browser,
    evidence_dir,
    pytest_runtest_makereport,
    pytest_sessionfinish,
    stack,
)
