"""Run the real-service browser acceptance suite in tests/browser.

The suite starts its own FastAPI coordinator (AI_PROVIDER=mock, credentials
blanked, throwaway data directory) and a production frontend bundle built
against it, then drives installed Chrome through Python Playwright. It needs
`npm ci` in frontend/. Evidence (screenshots, report.json, the downloaded
package) goes to backend/.work/browser-acceptance/<UTC stamp>/.

    backend/.venv/bin/python backend/scripts/browser_qa.py [pytest args]

is equivalent to `python -m pytest -m browser tests/browser` from backend/.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend = Path(__file__).resolve().parents[1]
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "browser",
            "tests/browser",
            *sys.argv[1:],
        ],
        cwd=backend,
    )


if __name__ == "__main__":
    raise SystemExit(main())
