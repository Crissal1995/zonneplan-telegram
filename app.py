"""
Vercel entrypoint for the Telegram webhook.

The application lives in the ``src`` layout (``src/zonneplan_telegram/vercel.py``), but
Vercel resolves ``tool.vercel.entrypoint`` as a module path relative to the project root,
so it would look for ``./zonneplan_telegram/vercel.py``. This module gives the entrypoint
a file it can actually find and exposes the FastAPI instance as ``app``.
"""

import sys
from pathlib import Path

# Make the src layout importable even when the deployment only installs dependencies.
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from zonneplan_telegram.vercel import app  # noqa: E402

__all__ = ["app"]
