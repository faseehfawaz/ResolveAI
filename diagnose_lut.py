#!/usr/bin/env python3
"""
ResolveAI – SetLUT Deep Diagnostic

Investigates why SetLUT returns False by trying various approaches:
1. Copy LUT to Resolve's official LUT directory
2. Try setting current clip first
3. Try different path formats
4. Check if Color page is active
"""

import sys, os, shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection

# Resolve's official LUT directories on macOS
RESOLVE_LUT_DIRS = [
    os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"),
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT",
]


def main():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  ResolveAI – SetLUT Deep Diagnostic             ║")
    print("╚══════════════════════════════════════════════════╝\n")

    conn = get_connection()
    if conn._resolve is None:
        print("❌ Could not connect to Resolve.")
        return

    resolve = conn.resolve
    timeline = conn.get_current_timeline()
    if not timeline:
        print("❌ No timeline active.")
        return

    items = timeline.GetItemListInTrack("video", 1)
    if not items:
        print("❌ No clips.")
        return

    item = items[0]
    name = item.GetName() or "unknown"
    print(f"🎞  Testing with clip: '{name}'")

    # Find a LUT file
    luts_dir = os.path.join(PROJECT_ROOT, "luts")
    lut_files = [f for f in os.listdir(luts_dir) if f.endswith(".cube")] if os.path.isdir(luts_dir) else []
    if not lut_files:
        print("❌ No .cube files in luts/ directory.")
        return

    original_lut = os.path.join(luts_dir, lut_files[0])
    print(f"   LUT: {lut_files[0]}")
    print(f"   Path: {original_lut}")
    print(f"   Exists: {os.path.isfile(original_lut)}")
    print(f"   Size: {os.path.getsize(original_lut)} bytes")

    # ── Test 1: Check current page ───────────────────────────
    print(f"\n─── Test 1: Check current page ─────────────────")
    try:
        page = resolve.GetCurrentPage()
        print(f"  Current page: '{page}'")
        if page != "color":
            print(f"  ⚠️  Not on Color page! Switching...")
            result = resolve.OpenPage("color")
            print(f"  OpenPage('color') → {result}")
            import time
            time.sleep(1)
            page = resolve.GetCurrentPage()
            print(f"  Now on: '{page}'")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 2: Try GetCurrentVideoItem ──────────────────────
    print(f"\n─── Test 2: Current video item ─────────────────")
    try:
        current = timeline.GetCurrentVideoItem()
        if current:
            cname = current.GetName() or "unknown"
            print(f"  Current clip: '{cname}'")
        else:
            print(f"  No current video item (None)")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 3: SetLUT with original path ────────────────────
    print(f"\n─── Test 3: SetLUT(1, original_path) ───────────")
    try:
        result = item.SetLUT(1, original_lut)
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 4: Copy LUT to Resolve's directory ──────────────
    print(f"\n─── Test 4: Copy to Resolve LUT directory ──────")
    resolve_lut_dir = None
    for d in RESOLVE_LUT_DIRS:
        if os.path.isdir(d):
            resolve_lut_dir = d
            break

    if resolve_lut_dir:
        # Create a ResolveAI subfolder
        ai_lut_dir = os.path.join(resolve_lut_dir, "ResolveAI")
        os.makedirs(ai_lut_dir, exist_ok=True)
        dest_lut = os.path.join(ai_lut_dir, lut_files[0])
        shutil.copy2(original_lut, dest_lut)
        print(f"  Copied to: {dest_lut}")
        print(f"  Exists: {os.path.isfile(dest_lut)}")

        try:
            result = item.SetLUT(1, dest_lut)
            print(f"  SetLUT(1, resolve_dir_path) → {result}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print(f"  ⚠️  Could not find Resolve LUT directory")
        for d in RESOLVE_LUT_DIRS:
            print(f"       Checked: {d} → {'exists' if os.path.isdir(d) else 'NOT FOUND'}")

    # ── Test 5: Try with GetCurrentVideoItem ─────────────────
    print(f"\n─── Test 5: SetLUT on current video item ───────")
    try:
        current = timeline.GetCurrentVideoItem()
        if current:
            result = current.SetLUT(1, original_lut)
            print(f"  SetLUT on current item → {result}")
        else:
            print(f"  No current video item")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 6: Try GetNodeGraph ─────────────────────────────
    print(f"\n─── Test 6: Explore NodeGraph ──────────────────")
    try:
        ng = item.GetNodeGraph()
        if ng:
            print(f"  NodeGraph type: {type(ng).__name__}")
            # List available methods
            methods = [m for m in dir(ng) if not m.startswith('_')]
            print(f"  Available methods: {methods}")

            # Try to get node count
            try:
                count = ng.GetNodeCount() if hasattr(ng, 'GetNodeCount') else "N/A"
                print(f"  NodeCount: {count}")
            except:
                pass

            # Try GetNodes or GetNodeList
            for method_name in ['GetNodes', 'GetNodeList', 'GetNumNodes', 'GetSize']:
                try:
                    fn = getattr(ng, method_name, None)
                    if fn:
                        result = fn()
                        print(f"  {method_name}() → {result}")
                except Exception as e:
                    print(f"  {method_name}() → Error: {e}")

            # Try to get LUT status
            for method_name in ['GetLUT', 'GetNodeLUT']:
                try:
                    fn = getattr(ng, method_name, None)
                    if fn:
                        result = fn(1)
                        print(f"  {method_name}(1) → {result}")
                except Exception as e:
                    print(f"  {method_name}(1) → Error: {e}")
        else:
            print(f"  GetNodeGraph() returned None")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 7: GetLUT to check current state ────────────────
    print(f"\n─── Test 7: GetLUT (check current state) ───────")
    try:
        lut = item.GetLUT(1)
        print(f"  GetLUT(1) → {lut}")
    except Exception as e:
        print(f"  Error: {e}")

    try:
        lut = item.GetLUT({"NodeIndex": 1})
        print(f"  GetLUT({{'NodeIndex':1}}) → {lut}")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Test 8: Try SetProperty for Color ────────────────────
    print(f"\n─── Test 8: Explore SetProperty ────────────────")
    try:
        # Get all properties
        props = item.GetProperty()
        if props and isinstance(props, dict):
            print(f"  Properties ({len(props)} total):")
            for k, v in sorted(props.items()):
                if any(term in k.lower() for term in ['color', 'lut', 'grade', 'cdl', 'node', 'curve']):
                    print(f"    {k}: {v}")
        elif props:
            print(f"  Properties: {type(props).__name__}")
    except Exception as e:
        print(f"  Error: {e}")

    print()


if __name__ == "__main__":
    main()
