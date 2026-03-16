#!/usr/bin/env python3
"""
ResolveAI – Exhaustive SetLUT Test

Creates a minimal identity LUT and tries every possible way to apply it.
"""

import sys, os, time
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection


def create_minimal_identity_lut(path):
    """Create a tiny 2x2x2 identity LUT."""
    with open(path, "w") as f:
        f.write('TITLE "Identity"\n')
        f.write('LUT_3D_SIZE 2\n')
        f.write('\n')
        # 2x2x2 = 8 entries, identity mapping
        # B=0, G=0: R varies
        f.write('0.0 0.0 0.0\n')  # R=0 G=0 B=0
        f.write('1.0 0.0 0.0\n')  # R=1 G=0 B=0
        # B=0, G=1: R varies
        f.write('0.0 1.0 0.0\n')  # R=0 G=1 B=0
        f.write('1.0 1.0 0.0\n')  # R=1 G=1 B=0
        # B=1, G=0: R varies
        f.write('0.0 0.0 1.0\n')  # R=0 G=0 B=1
        f.write('1.0 0.0 1.0\n')  # R=1 G=0 B=1
        # B=1, G=1: R varies
        f.write('0.0 1.0 1.0\n')  # R=0 G=1 B=1
        f.write('1.0 1.0 1.0\n')  # R=1 G=1 B=1
    print(f"  Created identity LUT: {path} ({os.path.getsize(path)} bytes)")


def create_standard_identity_lut(path, size=17):
    """Create a standard-size identity LUT."""
    with open(path, "w") as f:
        f.write(f'TITLE "Identity_{size}"\n')
        f.write(f'LUT_3D_SIZE {size}\n')
        f.write('DOMAIN_MIN 0.0 0.0 0.0\n')
        f.write('DOMAIN_MAX 1.0 1.0 1.0\n')
        f.write('\n')
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    r = ri / (size - 1)
                    g = gi / (size - 1)
                    b = bi / (size - 1)
                    f.write(f'{r:.6f} {g:.6f} {b:.6f}\n')
    print(f"  Created identity LUT: {path} ({os.path.getsize(path)} bytes)")


def main():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  ResolveAI – Exhaustive SetLUT Test              ║")
    print("╚══════════════════════════════════════════════════╝\n")

    conn = get_connection()
    if conn._resolve is None:
        print("❌ Could not connect.")
        return

    resolve = conn.resolve
    timeline = conn.get_current_timeline()
    items = timeline.GetItemListInTrack("video", 1)
    item = items[0]
    ng = item.GetNodeGraph()
    name = item.GetName()
    print(f"🎞  Clip: '{name}'")
    print(f"   Page: '{resolve.GetCurrentPage()}'")
    print(f"   Nodes: {ng.GetNumNodes()}")

    # Create test LUTs
    luts_dir = os.path.join(PROJECT_ROOT, "luts")
    os.makedirs(luts_dir, exist_ok=True)

    tiny_lut = os.path.join(luts_dir, "test_identity_2.cube")
    small_lut = os.path.join(luts_dir, "test_identity_17.cube")
    std_lut = os.path.join(luts_dir, "test_identity_33.cube")

    print("\n─── Creating test LUTs ─────────────────────────")
    create_minimal_identity_lut(tiny_lut)
    create_standard_identity_lut(small_lut, size=17)
    create_standard_identity_lut(std_lut, size=33)

    # Try ALL combinations
    test_luts = [
        ("tiny 2³", tiny_lut),
        ("small 17³", small_lut),
        ("standard 33³", std_lut),
    ]

    node_ids = [1, "1", 0, "0"]

    print(f"\n─── NodeGraph.SetLUT tests ─────────────────────")
    for lut_name, lut_path in test_luts:
        for nid in node_ids:
            try:
                result = ng.SetLUT(nid, lut_path)
                status = "✅" if result else "❌"
                print(f"  {status} ng.SetLUT({nid!r}, {lut_name}) → {result}")
                if result:
                    print(f"       >>> SUCCESS! Node ID={nid!r}, LUT={lut_name}")
                    return  # Found it!
            except Exception as e:
                print(f"  ⚠️  ng.SetLUT({nid!r}, {lut_name}) → {type(e).__name__}: {e}")

    print(f"\n─── TimelineItem.SetLUT tests ──────────────────")
    for lut_name, lut_path in test_luts:
        for nid in node_ids:
            try:
                result = item.SetLUT(nid, lut_path)
                status = "✅" if result else "❌"
                print(f"  {status} item.SetLUT({nid!r}, {lut_name}) → {result}")
                if result:
                    print(f"       >>> SUCCESS!")
                    return
            except Exception as e:
                print(f"  ⚠️  item.SetLUT({nid!r}, {lut_name}) → {type(e).__name__}: {e}")

    # Try ApplyArriCdlLut on NodeGraph
    print(f"\n─── NodeGraph.ApplyArriCdlLut tests ────────────")
    for lut_name, lut_path in test_luts:
        try:
            result = ng.ApplyArriCdlLut(lut_path)
            status = "✅" if result else "❌"
            print(f"  {status} ng.ApplyArriCdlLut({lut_name}) → {result}")
            if result:
                print(f"       >>> SUCCESS with ApplyArriCdlLut!")
                return
        except Exception as e:
            print(f"  ⚠️  ng.ApplyArriCdlLut({lut_name}) → {type(e).__name__}: {e}")

    # Try GetToolsInNode to understand node structure
    print(f"\n─── Node structure analysis ────────────────────")
    try:
        tools = ng.GetToolsInNode(1)
        print(f"  GetToolsInNode(1) → {tools}")
    except Exception as e:
        print(f"  GetToolsInNode(1) → {e}")

    try:
        tools = ng.GetToolsInNode("1")
        print(f"  GetToolsInNode('1') → {tools}")
    except Exception as e:
        print(f"  GetToolsInNode('1') → {e}")

    try:
        label = ng.GetNodeLabel(1)
        print(f"  GetNodeLabel(1) → '{label}'")
    except Exception as e:
        print(f"  GetNodeLabel(1) → {e}")

    # Print all ng methods with descriptions
    print(f"\n─── NodeGraph dir() ────────────────────────────")
    for attr in dir(ng):
        if not attr.startswith('_'):
            print(f"  {attr}")

    print(f"\n❌ All SetLUT attempts failed.")
    print(f"   The Resolve API SetLUT may not work via scripting in v20.3.")
    print(f"   Alternative: use CDL with enhanced S-curve approximation.\n")


if __name__ == "__main__":
    main()
