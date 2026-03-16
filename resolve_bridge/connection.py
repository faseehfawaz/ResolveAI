"""
ResolveAI – DaVinci Resolve Connection Manager

Connects to a running DaVinci Resolve Studio instance via the scripting API.
"""

import sys
import os
import importlib


def _get_resolve_script_module():
    """
    Locate and import the DaVinciResolveScript module.
    
    DaVinci Resolve installs the scripting API at a known location on macOS.
    We try multiple strategies:
      1. Check if it's already importable (env vars set)
      2. Add the known macOS path to sys.path
      3. Fall back to the RESOLVE_SCRIPT_API env var
    """
    # Strategy 1: already on sys.path
    try:
        import DaVinciResolveScript as dvr
        return dvr
    except ImportError:
        pass

    # Strategy 2: known macOS paths
    mac_paths = [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        os.path.expanduser(
            "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        ),
    ]
    for p in mac_paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    
    try:
        import DaVinciResolveScript as dvr
        return dvr
    except ImportError:
        pass

    # Strategy 3: RESOLVE_SCRIPT_API env var
    api_path = os.environ.get("RESOLVE_SCRIPT_API")
    if api_path:
        modules_path = os.path.join(api_path, "Modules")
        if modules_path not in sys.path:
            sys.path.insert(0, modules_path)
        try:
            import DaVinciResolveScript as dvr
            return dvr
        except ImportError:
            pass

    return None


class ResolveConnection:
    """Manages connection to a running DaVinci Resolve instance."""

    def __init__(self):
        self._dvr_module = None
        self._resolve = None

    def connect(self):
        """
        Connect to the running DaVinci Resolve instance.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        self._dvr_module = _get_resolve_script_module()
        if self._dvr_module is None:
            print("[ResolveAI] ERROR: Could not find DaVinciResolveScript module.")
            print("  Make sure DaVinci Resolve Studio is installed and the")
            print("  scripting API paths are configured correctly.")
            return False

        self._resolve = self._dvr_module.scriptapp("Resolve")
        if self._resolve is None:
            print("[ResolveAI] ERROR: Could not connect to DaVinci Resolve.")
            print("  Make sure DaVinci Resolve Studio is running.")
            return False

        print(f"[ResolveAI] Connected to DaVinci Resolve successfully.")
        return True

    @property
    def resolve(self):
        """The Resolve scripting API root object."""
        if self._resolve is None:
            raise RuntimeError("Not connected to DaVinci Resolve. Call connect() first.")
        return self._resolve

    def get_project_manager(self):
        """Get the Project Manager object."""
        return self.resolve.GetProjectManager()

    def get_current_project(self):
        """Get the currently open project."""
        pm = self.get_project_manager()
        if pm is None:
            return None
        return pm.GetCurrentProject()

    def get_current_timeline(self):
        """Get the currently active timeline in the open project."""
        project = self.get_current_project()
        if project is None:
            return None
        return project.GetCurrentTimeline()

    def get_media_pool(self):
        """Get the Media Pool object from the current project."""
        project = self.get_current_project()
        if project is None:
            return None
        return project.GetMediaPool()

    def get_fusion(self):
        """Get the Fusion object for Fusion page scripting."""
        return self.resolve.Fusion()

    def get_project_name(self):
        """Get the name of the currently open project."""
        project = self.get_current_project()
        if project is None:
            return None
        return project.GetName()

    def get_timeline_name(self):
        """Get the name of the currently active timeline."""
        timeline = self.get_current_timeline()
        if timeline is None:
            return None
        return timeline.GetName()


# ── Module-level convenience ─────────────────────────────────

_connection = None


def set_connection(conn):
    """Register an existing ResolveConnection as the module-level singleton."""
    global _connection
    _connection = conn


def get_connection():
    """Get the singleton ResolveConnection. Auto-connects if needed."""
    global _connection
    if _connection is None:
        _connection = ResolveConnection()
    # Auto-connect if not yet connected
    if _connection._resolve is None:
        _connection.connect()
    return _connection


def get_resolve():
    """Quick access: get the connected Resolve object."""
    conn = get_connection()
    return conn.resolve


def get_project():
    """Quick access: get the current project."""
    return get_connection().get_current_project()


def get_timeline():
    """Quick access: get the current timeline."""
    return get_connection().get_current_timeline()
