"""Vercel Python entry for every LabLess /api route.

The Vite app is static. vercel.json sends /api/* here, on the same origin.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.http_path import api_path
from app.tools import load_env
from run import Handler

load_env(ROOT / ".env")


class handler(Handler):
    """The same handler as `python run.py`, on one serverless function."""

    def _browser_path(self):
        self.path = api_path(self.path, self.headers)

    def do_GET(self):
        self._browser_path()
        return super().do_GET()

    def do_POST(self):
        self._browser_path()
        return super().do_POST()
