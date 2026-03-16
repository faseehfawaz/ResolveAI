#!/usr/bin/env python3
"""
ResolveAI – API Diagnostic Script

Probes the running DaVinci Resolve instance to discover which
scripting API methods are actually available on TimelineItem objects.
This helps us determine the correct approach for applying grades.

Usage:
    source .venv/bin/activate
    python diagnose_api.py
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection


def main():
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║       ResolveAI – API Diagnostic                       ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    conn = get_connection()
    if conn._resolve is None:
        print("❌ Could not connect to DaVinci Resolve.")
        return

    resolve = conn.resolve
    print(f"✅ Connected to Resolve")

    # ── Check Resolve version ────────────────────────────────
    try:
        version = resolve.GetVersionString()
        print(f"   Version: {version}")
    except Exception:
        print("   Version: (could not detect)")

    # ── Check product name (Studio vs Free) ──────────────────
    try:
        product = resolve.GetProductName()
        print(f"   Product: {product}")
    except Exception:
        print("   Product: (could not detect - may be Free version)")

    # ── Project & Timeline ───────────────────────────────────
    project = conn.get_current_project()
    if project is None:
        print("\n❌ No project open.")
        return
    print(f"\n📂 Project: {project.GetName()}")

    timeline = conn.get_current_timeline()
    if timeline is None:
        print("❌ No timeline active.")
        return
    print(f"🎬 Timeline: {timeline.GetName()}")

    # ── Get first clip ───────────────────────────────────────
    items = timeline.GetItemListInTrack("video", 1)
    if not items or len(items) == 0:
        print("❌ No clips on video track 1.")
        return

    item = items[0]
    clip_name = item.GetName() or "Unknown"
    print(f"\n🎞  Testing with clip: '{clip_name}'")

    # ── Probe TimelineItem methods ───────────────────────────
    print(f"\n─── TimelineItem Method Availability ─────────────────")

    methods_to_test = [
        # Color grading methods
        "SetCDL", "GetCDL",
        "SetLUT", "GetLUT",
        "SetClipColor", "GetClipColor", "ClearClipColor",
        "AddNode", "AddSerialNode",
        "GetNumNodes", "GetNodeCount",
        "ResetGrades", "DeleteNode",
        # Grade versioning
        "AddVersion", "GetCurrentVersion", "SetCurrentVersion",
        "GetVersionCount", "DeleteVersion",
        # Stills / grades
        "ApplyGradeFromDRX", "ExportGrade",
        "GrabStill", "ApplyStill",
        # Clip properties
        "GetName", "GetDuration", "GetStart", "GetEnd",
        "GetMediaPoolItem",
        "GetProperty", "SetProperty",
        "GetClipProperty",
        # Node graph
        "GetNodeGraph", "SetNodeGraph",
        "GetColorPage", "SetColorPage",
    ]

    available = []
    unavailable = []

    for method_name in methods_to_test:
        attr = getattr(item, method_name, None)
        if attr is not None and callable(attr):
            available.append(method_name)
            print(f"  ✅ {method_name}")
        else:
            unavailable.append(method_name)
            print(f"  ❌ {method_name}")

    # ── Try SetCDL ───────────────────────────────────────────
    print(f"\n─── Testing SetCDL ──────────────────────────────────")
    try:
        # Try setting an identity CDL (no change)
        cdl_identity = {
            "NodeIndex": 1,
            "Slope": {"Red": 1.0, "Green": 1.0, "Blue": 1.0},
            "Offset": {"Red": 0.0, "Green": 0.0, "Blue": 0.0},
            "Power": {"Red": 1.0, "Green": 1.0, "Blue": 1.0},
            "Saturation": 1.0,
        }
        result = item.SetCDL(cdl_identity)
        print(f"  SetCDL(dict) → {result} (type: {type(result).__name__})")
    except Exception as e:
        print(f"  SetCDL(dict) → Exception: {e}")

    # ── Try GetCDL ───────────────────────────────────────────
    print(f"\n─── Testing GetCDL ──────────────────────────────────")
    try:
        result = item.GetCDL({"NodeIndex": 1})
        print(f"  GetCDL({{'NodeIndex': 1}}) → {result}")
    except Exception as e:
        print(f"  GetCDL → Exception: {e}")

    # ── Try SetLUT with various signatures ───────────────────
    print(f"\n─── Testing SetLUT Signatures ───────────────────────")
    
    # Check if any LUT exists in luts/
    luts_dir = os.path.join(PROJECT_ROOT, "luts")
    lut_files = [f for f in os.listdir(luts_dir) if f.endswith(".cube")] if os.path.isdir(luts_dir) else []
    
    if lut_files:
        test_lut = os.path.join(luts_dir, lut_files[0])
        print(f"  Using LUT: {lut_files[0]}")
        
        signatures = [
            ("SetLUT(1, path)", lambda: item.SetLUT(1, test_lut)),
            ("SetLUT(path, 1)", lambda: item.SetLUT(test_lut, 1)),
            ("SetLUT(path)", lambda: item.SetLUT(test_lut)),
            ("SetLUT({'NodeIndex':1, 'LUTPath':p})", 
             lambda: item.SetLUT({"NodeIndex": 1, "LUTPath": test_lut})),
        ]
        
        for desc, fn in signatures:
            try:
                result = fn()
                print(f"  {desc} → {result} (type: {type(result).__name__})")
            except Exception as e:
                print(f"  {desc} → Exception: {type(e).__name__}: {e}")
    else:
        print("  ⚠️  No .cube LUT files found in luts/ directory")

    # ── Probe Timeline methods ───────────────────────────────
    print(f"\n─── Timeline Method Availability ────────────────────")
    
    timeline_methods = [
        "ApplyGradeFromDRX",
        "GrabStill", "GrabAllStills",
        "GetCurrentVideoItem",
        "GetItemListInTrack",
        "GetTrackCount",
        "GetSetting",
    ]
    
    for method_name in timeline_methods:
        attr = getattr(timeline, method_name, None)
        if attr is not None and callable(attr):
            print(f"  ✅ {method_name}")
        else:
            print(f"  ❌ {method_name}")

    # ── Summary ──────────────────────────────────────────────
    print(f"\n─── Summary ────────────────────────────────────────")
    print(f"  Available: {len(available)} methods")
    print(f"  Unavailable: {len(unavailable)} methods")
    
    if "SetCDL" in available:
        print(f"\n  💡 SetCDL is available — CDL-based grading should work!")
    if "SetLUT" in available:
        print(f"  💡 SetLUT is available — but may need correct signature")
    if "SetLUT" not in available:
        print(f"  ⚠️  SetLUT NOT available — will use CDL-only approach")
    
    print()


if __name__ == "__main__":
    main()
