"""
ResolveAI – Grading Application Helpers

Applies color grades (CDL, LUT, DRX) to timeline clips via the Resolve API.
"""

import os
from typing import Optional, Dict, Any, Tuple

from resolve_bridge.connection import get_timeline


# ── CDL Values ───────────────────────────────────────────────

def apply_cdl(
    timeline_item,
    slope: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    power: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    saturation: float = 1.0,
    node_index: int = 1,
) -> bool:
    """
    Apply CDL (Color Decision List) values to a specific node on a clip.
    
    Args:
        timeline_item: The Resolve TimelineItem object.
        slope: (R, G, B) slope values – controls gain/highlights.
        offset: (R, G, B) offset values – controls shadows/lift.
        power: (R, G, B) power values – controls gamma/midtones.
        saturation: Overall saturation multiplier.
        node_index: 1-based index of the corrector node to modify.
    
    Returns:
        True if CDL was applied successfully.
    """
    try:
        cdl_map = {
            "NodeIndex": node_index,
            "Slope": {"Red": slope[0], "Green": slope[1], "Blue": slope[2]},
            "Offset": {"Red": offset[0], "Green": offset[1], "Blue": offset[2]},
            "Power": {"Red": power[0], "Green": power[1], "Blue": power[2]},
            "Saturation": saturation,
        }
        result = timeline_item.SetCDL(cdl_map)
        if result:
            clip_name = timeline_item.GetName() or "unknown"
            print(f"[ResolveAI] Applied CDL to node {node_index} on '{clip_name}'")
        return bool(result)
    except Exception as e:
        print(f"[ResolveAI] Error applying CDL: {e}")
        return False


def get_cdl(timeline_item, node_index: int = 1) -> Optional[Dict]:
    """
    Read CDL values from a specific node on a clip.
    
    Returns:
        Dict with Slope, Offset, Power, Saturation or None on error.
    """
    try:
        return timeline_item.GetCDL({"NodeIndex": node_index})
    except Exception as e:
        print(f"[ResolveAI] Error reading CDL: {e}")
        return None


# ── LUT Application ──────────────────────────────────────────

def apply_lut(
    timeline_item,
    lut_path: str,
    node_index: int = 1,
) -> bool:
    """
    Apply a .cube LUT file to a specific node on a clip.
    
    Tries multiple API call signatures for compatibility across
    different DaVinci Resolve versions.
    
    Args:
        timeline_item: The Resolve TimelineItem object.
        lut_path: Absolute path to the .cube LUT file.
        node_index: 1-based index of the corrector node.
    
    Returns:
        True if LUT was applied successfully.
    """
    if not os.path.isfile(lut_path):
        print(f"[ResolveAI] LUT file not found: {lut_path}")
        return False

    clip_name = timeline_item.GetName() or "unknown"
    lut_name = os.path.basename(lut_path)

    # Try multiple SetLUT signatures (varies by Resolve version)
    strategies = [
        # Strategy 1: SetLUT(nodeIndex, lutPath) – most common
        lambda: timeline_item.SetLUT(node_index, lut_path),
        # Strategy 2: SetLUT({"nodeIndex": n, "lutPath": path})
        lambda: timeline_item.SetLUT({"NodeIndex": node_index, "LUTPath": lut_path}),
        # Strategy 3: Just the path (applies to current/first node)
        lambda: timeline_item.SetLUT(lut_path),
    ]

    for i, strategy in enumerate(strategies):
        try:
            result = strategy()
            if result:
                print(f"[ResolveAI] Applied LUT '{lut_name}' to node {node_index} "
                      f"on '{clip_name}'")
                return True
        except TypeError:
            continue  # Wrong signature, try next
        except Exception as e:
            if i == len(strategies) - 1:
                print(f"[ResolveAI] Error applying LUT to '{clip_name}': {e}")
            continue

    # If SetLUT didn't work, try applying via the MediaPoolItem's clip property
    try:
        mpi = timeline_item.GetMediaPoolItem()
        if mpi:
            result = mpi.SetClipProperty("LUT", lut_path)
            if result:
                print(f"[ResolveAI] Applied LUT '{lut_name}' via clip property "
                      f"on '{clip_name}'")
                return True
    except Exception:
        pass

    print(f"[ResolveAI] WARNING: Could not apply LUT to '{clip_name}' via API. "
          f"LUT file saved at: {lut_path}")
    print(f"[ResolveAI] TIP: You can manually apply this LUT in Resolve's Color page "
          f"(right-click node → LUT → Browse)")
    return False


# ── DRX Grade Application ────────────────────────────────────

def apply_drx(
    timeline_item,
    drx_path: str,
    grade_mode: int = 0,
) -> bool:
    """
    Apply a saved grade from a .drx (DaVinci Resolve eXchange) file.
    
    Uses the NodeGraph.ApplyGradeFromDRX() API which is confirmed working
    in Resolve Studio 20.3.
    
    Args:
        timeline_item: The Resolve TimelineItem object.
        drx_path: Absolute path to the .drx file.
        grade_mode: 0 = apply to current version, 1 = create new version.
    
    Returns:
        True if grade was applied successfully.
    """
    if not os.path.isfile(drx_path):
        print(f"[ResolveAI] DRX file not found: {drx_path}")
        return False

    clip_name = timeline_item.GetName() or "unknown"

    try:
        # Get the NodeGraph object — this is the correct API path
        ng = timeline_item.GetNodeGraph()
        if ng is None:
            print(f"[ResolveAI] Could not get NodeGraph for '{clip_name}'")
            return False

        result = ng.ApplyGradeFromDRX(drx_path, grade_mode)
        if result:
            print(f"[ResolveAI] ✅ Applied DRX grade to '{clip_name}'")
            return True
        else:
            print(f"[ResolveAI] ❌ ApplyGradeFromDRX returned False for '{clip_name}'")
            return False
    except Exception as e:
        print(f"[ResolveAI] Error applying DRX to '{clip_name}': {e}")
        return False


# ── Node Management ──────────────────────────────────────────

def get_node_count(timeline_item) -> int:
    """
    Get the number of corrector nodes on a clip.
    
    Note: Not all Resolve versions expose this method.
    Returns 1 as fallback (every clip has at least one node).
    """
    try:
        count = timeline_item.GetNumNodes()
        if count and count > 0:
            return count
    except Exception:
        pass
    return 1  # Every clip always has at least node 1


def add_serial_node(timeline_item) -> int:
    """
    Try to add a new serial corrector node after the last existing node.
    
    Falls back gracefully to node 1 if the API doesn't support AddNode.
    
    Returns:
        The index (1-based) of the node to use.
    """
    # Try AddNode (may not be available in all Resolve versions)
    try:
        result = timeline_item.AddNode()
        if result:
            new_count = get_node_count(timeline_item)
            clip_name = timeline_item.GetName() or "unknown"
            print(f"[ResolveAI] Added serial node #{new_count} to '{clip_name}'")
            return new_count
    except Exception:
        pass

    # Try AddSerialNode
    try:
        result = timeline_item.AddSerialNode()
        if result:
            new_count = get_node_count(timeline_item)
            clip_name = timeline_item.GetName() or "unknown"
            print(f"[ResolveAI] Added serial node #{new_count} to '{clip_name}'")
            return new_count
    except Exception:
        pass

    # Fallback: use node 1 (always exists)
    return 1


def reset_all_grades(timeline_item) -> bool:
    """
    Reset all grading on a clip.
    
    Returns:
        True if reset was successful.
    """
    try:
        # Try ResetGrades first
        result = timeline_item.ResetGrades()
        if result:
            clip_name = timeline_item.GetName() or "unknown"
            print(f"[ResolveAI] Reset grades on '{clip_name}'")
            return True
    except Exception:
        pass

    try:
        result = timeline_item.ClearClipColor()
        clip_name = timeline_item.GetName() or "unknown"
        print(f"[ResolveAI] Reset clip color on '{clip_name}'")
        return True
    except Exception as e:
        print(f"[ResolveAI] Error resetting grades: {e}")
        return False


# ── Batch Application ────────────────────────────────────────

def apply_lut_to_clips(clips, lut_paths: Dict[int, str], node_label: str = "ResolveAI") -> int:
    """
    Apply per-clip LUTs to a list of clips.
    
    Args:
        clips: List of ClipInfo objects.
        lut_paths: Dict mapping clip index → LUT file path.
        node_label: Label for the node (for identification).
    
    Returns:
        Number of clips successfully graded.
    """
    success_count = 0

    for i, clip in enumerate(clips):
        lut_path = lut_paths.get(i)
        if lut_path is None:
            continue

        item = clip.timeline_item

        # Try to add a new node, fall back to node 1
        target_node = add_serial_node(item)

        if apply_lut(item, lut_path, node_index=target_node):
            success_count += 1

    return success_count


def apply_cdl_to_clips(
    clips,
    cdl_values: Dict[int, Dict],
    node_index: int = 1,
) -> int:
    """
    Apply per-clip CDL values to a list of clips.
    
    Args:
        clips: List of ClipInfo objects.
        cdl_values: Dict mapping clip index → CDL dict with slope, offset, power, sat.
        node_index: Which node to apply to (1-based).
    
    Returns:
        Number of clips successfully graded.
    """
    success_count = 0

    for i, clip in enumerate(clips):
        cdl = cdl_values.get(i)
        if cdl is None:
            continue

        item = clip.timeline_item
        if apply_cdl(
            item,
            slope=cdl.get("slope", (1, 1, 1)),
            offset=cdl.get("offset", (0, 0, 0)),
            power=cdl.get("power", (1, 1, 1)),
            saturation=cdl.get("saturation", 1.0),
            node_index=node_index,
        ):
            success_count += 1

    return success_count
