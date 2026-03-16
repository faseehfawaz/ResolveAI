#!/usr/bin/env python3
"""Quick test: Apply DRX grade via NodeGraph.ApplyGradeFromDRX()"""

import sys, os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection

conn = get_connection()
timeline = conn.get_current_timeline()
items = timeline.GetItemListInTrack("video", 1)
item = items[0]
name = item.GetName()
ng = item.GetNodeGraph()

drx_path = os.path.join(PROJECT_ROOT, "samplestills", "Still 2026-03-17 011434_1.1.2.drx")
print(f"Clip: {name}")
print(f"DRX:  {os.path.basename(drx_path)}")
print(f"Exists: {os.path.isfile(drx_path)}")

print(f"\n--- Trying ApplyGradeFromDRX ---")

# Try various signatures
tests = [
    ("ng.ApplyGradeFromDRX(path)", lambda: ng.ApplyGradeFromDRX(drx_path)),
    ("ng.ApplyGradeFromDRX(path, 0)", lambda: ng.ApplyGradeFromDRX(drx_path, 0)),
    ("ng.ApplyGradeFromDRX(path, 1)", lambda: ng.ApplyGradeFromDRX(drx_path, 1)),
    ("item.ApplyArriCdlLut(path)", lambda: item.ApplyArriCdlLut(drx_path) if hasattr(item, 'ApplyArriCdlLut') else "N/A"),
]

for label, fn in tests:
    try:
        result = fn()
        status = "✅" if result else "❌"
        print(f"  {status} {label} → {result}")
        if result:
            print(f"       >>> SUCCESS!")
    except Exception as e:
        print(f"  ⚠️  {label} → {type(e).__name__}: {e}")

print("\nDone! Check the Color page in Resolve.")
