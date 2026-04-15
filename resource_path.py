"""
PyInstaller-compatible path resolver.
When running from a PyInstaller bundle, files bundled via --add-data
are extracted to a temporary folder (sys._MEIPASS).
When running from source, paths resolve relative to this script's directory.
"""
import sys
import os


def resource_path(relative_path):
    """
    Get the absolute path to a resource, works for dev and for PyInstaller.
    
    Args:
        relative_path: Path relative to the project root (e.g. "assets/fonts")
        
    Returns:
        Absolute path that works in both source and bundled environments.
    """
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running from source
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


def app_dir():
    """
    Get the directory where the application EXE lives (or project root in dev).
    Use this for files that should persist alongside the EXE (settings, models, logs)
    — NOT for bundled read-only assets.
    
    Returns:
        Absolute path to the application's directory.
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle — use the EXE's directory
        return os.path.dirname(sys.executable)
    else:
        # Running from source — use the script's directory
        return os.path.dirname(os.path.abspath(__file__))
