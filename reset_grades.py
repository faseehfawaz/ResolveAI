#!/usr/bin/env python3
"""
ResolveAI – Reset all clip grades to default.

Run this to undo any CDL/LUT changes made by the plugin.

Usage:
    source .venv/bin/activate
    python reset_grades.py
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection


def main():
    print("\n[ResolveAI] Resetting all clip grades...\n")

    conn = get_connection()
    if conn._resolve is None:
        print("❌ Could not connect to Resolve.")
        return

    timeline = conn.get_current_timeline()
    if timeline is None:
        print("❌ No timeline active.")
        return

    items = timeline.GetItemListInTrack("video", 1)
    if not items:
        print("❌ No clips found.")
        return

    # Reset CDL to identity on all clips
    identity_cdl = {
        "NodeIndex": "1",
        "Slope": "1 1 1",
        "Offset": "0 0 0",
        "Power": "1 1 1",
        "Saturation": "1",
    }

    for item in items:
        name = item.GetName() or "unknown"
        try:
            result = item.SetCDL(identity_cdl)
            if result:
                print(f"  ✅ Reset '{name}'")
            else:
                print(f"  ⚠️  SetCDL returned False for '{name}'")
        except Exception as e:
            print(f"  ❌ Error resetting '{name}': {e}")

    print(f"\n[ResolveAI] Done! Reset {len(items)} clips to default.\n")


if __name__ == "__main__":
    main()
