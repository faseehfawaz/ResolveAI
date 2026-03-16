"""
ResolveAI – Exposure & White Balance Normalizer

Computes correction values to normalize clips to a common baseline
before applying a creative grade. This ensures mixed-camera footage
arrives at a consistent starting point.

IMPORTANT: The normalizer uses a "dead zone" approach — if footage
is already within a reasonable range of the target, corrections are
zero. This prevents overexposing well-exposed footage. Only clips
that are significantly off will receive meaningful corrections.
"""

import numpy as np
from typing import Tuple, Dict

from config import TARGET_LUMINANCE, TARGET_COLOR_TEMP

# ── Dead Zone Thresholds ─────────────────────────────────────
# If the measured value is within this tolerance of the target,
# no correction is applied. This prevents over-correcting
# footage that's already properly exposed.
EXPOSURE_DEAD_ZONE = 0.15     # ±0.15 luminance → no exposure correction
WHITE_BALANCE_DEAD_ZONE = 0.05  # ±5% channel ratio → no WB correction


def compute_exposure_correction(
    luminance_mean: float,
    luminance_std: float,
    target_luminance: float = None,
) -> Dict:
    """
    Compute CDL values to correct exposure to a target luminance level.
    
    Uses a dead zone: if the clip is within EXPOSURE_DEAD_ZONE of the
    target luminance, returns identity CDL (no change). This prevents
    brightening already well-exposed footage.
    
    Args:
        luminance_mean: Current average luminance (0–1).
        luminance_std: Current luminance standard deviation (0–1).
        target_luminance: Desired luminance level (0–1).
    
    Returns:
        Dict with CDL values: slope (R,G,B), offset (R,G,B), power (R,G,B).
    """
    if target_luminance is None:
        target_luminance = TARGET_LUMINANCE

    lum_diff = target_luminance - luminance_mean

    # ── Dead zone: skip correction for well-exposed footage ──
    if abs(lum_diff) < EXPOSURE_DEAD_ZONE:
        return {
            "slope": (1.0, 1.0, 1.0),
            "offset": (0.0, 0.0, 0.0),
            "power": (1.0, 1.0, 1.0),
            "saturation": 1.0,
        }

    # Outside dead zone: apply gentle correction
    # Only correct the portion beyond the dead zone
    effective_diff = lum_diff - (EXPOSURE_DEAD_ZONE if lum_diff > 0 else -EXPOSURE_DEAD_ZONE)

    # Very gentle offset correction
    offset_val = effective_diff * 0.08
    offset_val = max(-0.02, min(0.02, offset_val))

    # Power correction: only for significantly mis-exposed clips
    # Keep very close to 1.0
    power_val = 1.0
    if abs(effective_diff) > 0.1:
        # Only slight gamma correction for very dark/bright clips
        power_val = 1.0 - (effective_diff * 0.15)
        power_val = max(0.9, min(1.1, power_val))

    slope_val = 1.0

    return {
        "slope": (slope_val, slope_val, slope_val),
        "offset": (offset_val, offset_val, offset_val),
        "power": (power_val, power_val, power_val),
        "saturation": 1.0,
    }


def compute_white_balance_correction(
    r_mean: float,
    g_mean: float,
    b_mean: float,
    target_temp: float = None,
) -> Dict:
    """
    Compute CDL slope values to correct white balance toward a target temperature.
    
    White balance correction works by adjusting the per-channel gains (slope in CDL)
    to neutralize any color cast. Uses a dead zone to avoid correcting footage
    that already has reasonable white balance.
    
    Args:
        r_mean: Average red channel value (0–255).
        g_mean: Average green channel value (0–255).
        b_mean: Average blue channel value (0–255).
        target_temp: Target color temperature in Kelvin.
    
    Returns:
        Dict with CDL slope values to correct white balance.
    """
    if target_temp is None:
        target_temp = TARGET_COLOR_TEMP

    # Avoid division by zero
    r_mean = max(r_mean, 1.0)
    g_mean = max(g_mean, 1.0)
    b_mean = max(b_mean, 1.0)

    # ── Compute how far off the white balance is ─────────────
    # Check if R and B are already close to G (balanced)
    r_ratio = r_mean / g_mean
    b_ratio = b_mean / g_mean

    # Dead zone: if channels are within 5% of each other, skip
    r_needs_correction = abs(r_ratio - 1.0) > WHITE_BALANCE_DEAD_ZONE
    b_needs_correction = abs(b_ratio - 1.0) > WHITE_BALANCE_DEAD_ZONE

    # Compute slopes only for channels that need correction
    if r_needs_correction:
        target_r_slope = g_mean / r_mean
        # Blend toward 1.0 to make it subtle
        r_slope = 1.0 + (target_r_slope - 1.0) * 0.5
    else:
        r_slope = 1.0

    if b_needs_correction:
        target_b_slope = g_mean / b_mean
        b_slope = 1.0 + (target_b_slope - 1.0) * 0.5
    else:
        b_slope = 1.0

    g_slope = 1.0  # Green stays as reference

    # Now apply a temperature shift if the target isn't neutral (6500K)
    # This is VERY gentle — just a subtle creative push
    temp_shift = (target_temp - 6500.0) / 6500.0
    r_slope *= (1.0 - temp_shift * 0.08)  # Reduced from 0.15
    b_slope *= (1.0 + temp_shift * 0.08)

    # Clamp slopes to tight range
    r_slope = max(0.85, min(1.15, r_slope))
    g_slope = max(0.85, min(1.15, g_slope))
    b_slope = max(0.85, min(1.15, b_slope))

    return {
        "slope": (r_slope, g_slope, b_slope),
        "offset": (0.0, 0.0, 0.0),
        "power": (1.0, 1.0, 1.0),
        "saturation": 1.0,
    }


def compute_full_normalization(
    luminance_mean: float,
    luminance_std: float,
    r_mean: float,
    g_mean: float,
    b_mean: float,
    target_luminance: float = None,
    target_temp: float = None,
) -> Dict:
    """
    Compute combined exposure + white balance normalization as a single CDL.
    
    Returns:
        Dict with combined CDL values.
    """
    expo = compute_exposure_correction(luminance_mean, luminance_std, target_luminance)
    wb = compute_white_balance_correction(r_mean, g_mean, b_mean, target_temp)

    # Combine: multiply slopes, add offsets
    combined_slope = tuple(
        expo["slope"][i] * wb["slope"][i] for i in range(3)
    )
    combined_offset = expo["offset"]  # Only exposure contributes offset
    combined_power = expo["power"]    # Only exposure contributes power

    # Clamp all values tightly
    combined_slope = tuple(max(0.85, min(1.15, s)) for s in combined_slope)
    combined_offset = tuple(max(-0.02, min(0.02, o)) for o in combined_offset)
    combined_power = tuple(max(0.9, min(1.1, p)) for p in combined_power)

    return {
        "slope": combined_slope,
        "offset": combined_offset,
        "power": combined_power,
        "saturation": 1.0,
    }


def compute_normalization_for_profile(profile, target_luminance=None, target_temp=None) -> Dict:
    """
    Convenience function: compute normalization from a ClipColorProfile.
    
    Args:
        profile: A ClipColorProfile from analyzer.py.
    
    Returns:
        CDL dict for normalization.
    """
    return compute_full_normalization(
        luminance_mean=profile.luminance_mean,
        luminance_std=profile.luminance_std,
        r_mean=profile.red.mean,
        g_mean=profile.green.mean,
        b_mean=profile.blue.mean,
        target_luminance=target_luminance,
        target_temp=target_temp,
    )
