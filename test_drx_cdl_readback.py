"""
Test: Apply DRX to reference clip, then apply identity CDL.
If the look changes → DRX's CDL was non-identity.
If the look stays → DRX's CDL was identity (just curves).

Also tests: apply DRX, then SetCDL with a slight adjustment.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve_bridge.connection import ResolveConnection

def main():
    conn = ResolveConnection()
    if not conn.connect():
        return
    resolve = conn.resolve

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    tl = proj.GetCurrentTimeline()
    items = tl.GetItemListInTrack("video", 1)
    
    drx_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samplestills")
    drx_files = [f for f in os.listdir(drx_dir) if f.endswith(".drx")]
    drx_path = os.path.join(drx_dir, drx_files[-1])
    
    print(f"\nDRX: {os.path.basename(drx_path)}")
    print(f"Clips: {[i.GetName() for i in items]}")
    
    # --- Test on reference clip (C9492, clip index 2 = 3rd clip) ---
    ref_item = items[2]  # C9492
    print(f"\n{'='*50}")
    print(f"Reference clip: {ref_item.GetName()}")
    
    # Step 1: Reset
    ng = ref_item.GetNodeGraph()
    ng.ResetAllGrades()
    print("  1. Reset → look at Color page (should be raw)")
    input("     Press Enter to continue...")
    
    # Step 2: Apply DRX
    ng = ref_item.GetNodeGraph()
    result = ng.ApplyGradeFromDRX(drx_path, 0)
    print(f"  2. Applied DRX → {result} (should look graded)")
    input("     Press Enter to continue...")
    
    # Step 3: SetCDL to IDENTITY (1,1,1 / 0,0,0 / 1,1,1)
    identity_cdl = {
        "NodeIndex": "1",
        "Slope": "1.0 1.0 1.0",
        "Offset": "0.0 0.0 0.0",
        "Power": "1.0 1.0 1.0",
        "Saturation": "1.0",
    }
    result = ref_item.SetCDL(identity_cdl)
    print(f"  3. Set identity CDL → {result}")
    print("     LOOK AT COLOR PAGE NOW:")
    print("     - Same as step 2? → DRX CDL was identity")
    print("     - Different? → DRX CDL was non-identity (we're replacing it)")
    input("     Press Enter to continue...")
    
    # Step 4: Re-apply DRX to restore
    ng = ref_item.GetNodeGraph()
    ng.ApplyGradeFromDRX(drx_path, 0)
    print("  4. Re-applied DRX (restored)")
    
    # --- Now test on non-reference clip with correction ---
    test_item = items[0]  # C9484
    print(f"\n{'='*50}")
    print(f"Test clip: {test_item.GetName()}")
    
    # Apply DRX first
    ng = test_item.GetNodeGraph()
    ng.ResetAllGrades()
    ng = test_item.GetNodeGraph()
    ng.ApplyGradeFromDRX(drx_path, 0)
    print("  1. Applied DRX to test clip")
    input("     Press Enter to continue...")
    
    # Apply a SLIGHT correction CDL (just white balance, tiny adjustment)
    correction_cdl = {
        "NodeIndex": "1",
        "Slope": "1.02 1.00 0.98",
        "Offset": "0.0 0.0 0.0",
        "Power": "1.0 1.0 1.0",
        "Saturation": "1.0",
    }
    result = test_item.SetCDL(correction_cdl)
    print(f"  2. Set correction CDL (slope 1.02,1.0,0.98) → {result}")
    print("     LOOK AT COLOR PAGE:")
    print("     - Slightly warmer than step 1? → CDL works after DRX ✅")
    print("     - Same? → CDL has no effect after DRX ❌")
    
    print("\nDONE!")

if __name__ == "__main__":
    main()
