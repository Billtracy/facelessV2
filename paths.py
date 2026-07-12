"""
Path helpers that work both in development and inside a PyInstaller bundle.

Read-only files shipped with the app (assets, templates) -> resource_path()
Writable per-user files (settings, models, temp, logs)    -> user_data_root() / user_data_dir()
"""

import os
import sys

APP_DIR_NAME = "FacelessGenerator"


def is_frozen():
    """True when running from a PyInstaller bundle."""
    return getattr(sys, 'frozen', False)


def resource_path(*parts):
    """
    Absolute path to a read-only resource bundled with the app
    (e.g. resource_path("assets", "fonts", "Anton-Regular.ttf")).
    """
    if is_frozen():
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def app_dir():
    """Folder containing the executable (or the project root in dev)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_data_root():
    """
    Writable per-user folder for app data. The exe folder must never be
    used for writes: it may be read-only (Program Files) and the process
    cwd is unreliable when launched from a shortcut.
    """
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        root = os.path.join(base, APP_DIR_NAME)
    else:
        root = os.path.join(os.path.expanduser('~'), '.faceless_generator')
    os.makedirs(root, exist_ok=True)
    return root


def user_data_dir(*parts):
    """Writable subfolder under the user data root, created on demand."""
    path = os.path.join(user_data_root(), *parts)
    os.makedirs(path, exist_ok=True)
    return path
