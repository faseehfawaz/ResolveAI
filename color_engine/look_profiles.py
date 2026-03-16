"""
ResolveAI – Look Profile System

Defines predefined "look" profiles that describe target color characteristics
for creative grading styles like Corporate, Cinematic, etc.

Each profile specifies target values that the color engine will match
each clip to, producing a consistent look across the entire timeline.
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from config import LOOKS_DIR


@dataclass
class LookProfile:
    """
    Defines the target color characteristics for a creative look.
    
    These values describe the DESIRED output, and the color engine
    will compute a transform to get each clip from its current state
    to this target.
    """
    name: str = ""
    display_name: str = ""
    description: str = ""

    # ── Luminance Targets ────────────────────────────────────
    target_luminance: float = 0.45      # Target average brightness (0–1)
    contrast: float = 1.0               # Contrast multiplier (1.0 = neutral)
    shadow_lift: float = 0.0            # Lift blacks (> 0 = lifted)
    highlight_compression: float = 0.0  # Pull down highlights (> 0 = compressed)

    # ── Color Temperature ────────────────────────────────────
    target_temp: float = 6500.0         # Target color temperature
    tint_shift: float = 0.0            # Green-Magenta shift (-1 to 1)

    # ── Saturation ───────────────────────────────────────────
    saturation_multiplier: float = 1.0  # Global saturation adjustment
    vibrance: float = 0.0              # Boost low-saturation colors only

    # ── Split Toning ─────────────────────────────────────────
    shadow_tint: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # RGB offset for shadows
    highlight_tint: Tuple[float, float, float] = (0.0, 0.0, 0.0) # RGB offset for highlights
    midtone_tint: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # RGB offset for midtones

    # ── CDL Adjustments (applied on top of normalization) ────
    # These are relative adjustments, not absolute targets
    slope_adjust: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset_adjust: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    power_adjust: Tuple[float, float, float] = (1.0, 1.0, 1.0)


def load_look_profile(name: str) -> LookProfile:
    """
    Load a look profile from a JSON file.
    
    Args:
        name: Profile name (e.g., "corporate"). Looks in the looks/ directory.
    
    Returns:
        LookProfile object.
    """
    json_path = os.path.join(LOOKS_DIR, f"{name}.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Look profile not found: {json_path}")

    with open(json_path, "r") as f:
        data = json.load(f)

    profile = LookProfile()
    for key, value in data.items():
        if hasattr(profile, key):
            # Convert lists to tuples for tuple fields
            if isinstance(getattr(profile, key), tuple) and isinstance(value, list):
                value = tuple(value)
            setattr(profile, key, value)

    return profile


def save_look_profile(profile: LookProfile, output_path: str = None):
    """Save a look profile to a JSON file."""
    if output_path is None:
        output_path = os.path.join(LOOKS_DIR, f"{profile.name}.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data = asdict(profile)
    # Convert tuples to lists for JSON serialization
    for key, value in data.items():
        if isinstance(value, tuple):
            data[key] = list(value)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def list_available_looks() -> List[str]:
    """Return names of all available look profiles."""
    if not os.path.isdir(LOOKS_DIR):
        return []
    return [
        os.path.splitext(f)[0]
        for f in sorted(os.listdir(LOOKS_DIR))
        if f.endswith(".json")
    ]


def look_profile_to_target_stats(profile: LookProfile) -> Dict:
    """
    Convert a LookProfile into synthetic 'target' color statistics
    that can be used with the color transfer algorithms.
    
    This is used for "Auto-Grade to Look" mode, where there's no
    reference clip – the look profile itself defines the target.
    
    Returns:
        Dict with synthetic mean/std values for LAB channels.
    """
    # Map profile parameters to LAB statistics
    # These are calibrated synthetic values that produce good results

    # L channel: driven by target luminance and contrast
    l_mean = profile.target_luminance * 255.0 * 0.4  # LAB L range in OpenCV
    l_std = 50.0 * profile.contrast  # Higher contrast = wider L distribution

    # a channel: driven by tint (green-magenta axis)
    a_mean = 128.0 + profile.tint_shift * 15.0  # 128 is neutral in OpenCV LAB
    a_std = 10.0 + abs(profile.tint_shift) * 5.0

    # b channel: driven by color temperature (blue-yellow axis)
    temp_shift = (profile.target_temp - 6500.0) / 6500.0
    b_mean = 128.0 + temp_shift * 20.0  # Warm = higher b, cool = lower b
    b_std = 12.0

    return {
        "lab_l_mean": l_mean,
        "lab_l_std": l_std,
        "lab_a_mean": a_mean,
        "lab_a_std": a_std,
        "lab_b_mean": b_mean,
        "lab_b_std": b_std,
        "saturation_target": profile.saturation_multiplier,
    }
