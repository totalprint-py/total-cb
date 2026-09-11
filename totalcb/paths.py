"""Absolute path resolution for the total-cb desktop application.

Every runtime path resolves to an absolute location (Constitution Principle 4,
FR-011). Frozen PyInstaller builds unpack read-only assets under
``sys._MEIPASS`` and store the writable SQLite database under
``%LOCALAPPDATA%\\total-cb\\``; development uses the project root (``BASE_DIR``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root (dev): the directory that contains the ``totalcb/`` package.
BASE_DIR = Path(__file__).resolve().parent.parent

# Per-user application directory name used when frozen.
APP_DIR_NAME = "total-cb"


def app_root() -> Path:
    """Return the read-only root where bundled assets are unpacked.

    Frozen: ``sys._MEIPASS`` (PyInstaller extraction directory).
    Dev: ``BASE_DIR``.
    """
    return Path(getattr(sys, "_MEIPASS", BASE_DIR))


def data_dir() -> Path:
    """Return the per-user writable data directory, creating it if needed.

    Frozen: ``%LOCALAPPDATA%\\total-cb\\`` (falling back to the user's
    ``AppData\\Local`` when ``LOCALAPPDATA`` is unset).
    Dev: ``BASE_DIR``.
    """
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        base = Path(local_app_data) / APP_DIR_NAME
    else:
        base = BASE_DIR

    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    """Return the absolute path to the SQLite database file."""
    return data_dir() / "db.sqlite3"


def static_root() -> Path:
    """Return the absolute path to bundled static assets.

    Frozen: ``sys._MEIPASS\\static``. Dev: ``BASE_DIR\\static``.
    """
    return app_root() / "static"
