"""
ResolveAI – CDL Transform Calculator

Converts color analysis results into CDL (Color Decision List) values
that can be applied directly via DaVinci Resolve's SetCDL API.

CDL has per-channel:
  - Slope (gain/highlights)
  - Offset (lift/shadows)  
  - Power (gamma/midtones)
  - Saturation (global)

This module computes CDL corrections that approximate the full
color transfer between a source clip profile and a target profile.
"""

import numpy as np
from typing import Dict, Tuple

from color_engine.analyzer import ClipColorProfile


def compute_creative_cdl(
    source: ClipColorProfile,
    target: ClipColorProfile,
    intensity: float = 1.0,
) -> Dict:
    """
    Compute CDL values that transfer color from source → target profile.
    
    Uses per-channel statistics to compute slope (gain ratio),
    offset (mean shift), and power (gamma correction) that will
    bring the source clip's look closer to the target.
    
    Args:
        source: The source clip's analyzed color profile.
        target: The desired target color profile.
        intensity: Blend factor (0.0 = no change, 1.0 = full transfer).
    
    Returns:
        CDL dict with slope, offset, power, saturation.
    """
    # ── Per-channel slope: ratio of std deviations ───────────
    # This adjusts the contrast/dynamic range of each channel
    # to match the target's distribution width
    eps = 1e-6

    r_slope = (target.red.std / max(source.red.std, eps))
    g_slope = (target.green.std / max(source.green.std, eps))
    b_slope = (target.blue.std / max(source.blue.std, eps))

    # Clamp slopes to tight range for subtle correction
    r_slope = _clamp(r_slope, 0.8, 1.3)
    g_slope = _clamp(g_slope, 0.8, 1.3)
    b_slope = _clamp(b_slope, 0.8, 1.3)

    # ── Per-channel offset: mean shift after slope ───────────
    # offset = (target_mean - source_mean * slope) / 255
    # Normalized to 0-1 range for CDL
    r_offset = (target.red.mean - source.red.mean * r_slope) / 255.0
    g_offset = (target.green.mean - source.green.mean * g_slope) / 255.0
    b_offset = (target.blue.mean - source.blue.mean * b_slope) / 255.0

    # Clamp offsets tightly – even 0.05 is a big visual shift
    r_offset = _clamp(r_offset, -0.05, 0.05)
    g_offset = _clamp(g_offset, -0.05, 0.05)
    b_offset = _clamp(b_offset, -0.05, 0.05)

    # ── Power: gamma correction based on luminance ───────────
    # If source is darker than target in midtones, we need
    # power < 1 to lift midtones (and vice versa)
    src_gamma = _estimate_gamma(source)
    tgt_gamma = _estimate_gamma(target)
    
    if src_gamma > eps and tgt_gamma > eps:
        gamma_ratio = tgt_gamma / src_gamma
        gamma_ratio = _clamp(gamma_ratio, 0.6, 1.6)
    else:
        gamma_ratio = 1.0

    r_power = gamma_ratio
    g_power = gamma_ratio
    b_power = gamma_ratio

    # ── Saturation ───────────────────────────────────────────
    src_sat = max(source.saturation_mean, eps)
    tgt_sat = max(target.saturation_mean, eps) if target.saturation_mean else src_sat
    sat_ratio = tgt_sat / src_sat
    sat_ratio = _clamp(sat_ratio, 0.3, 2.0)

    # ── Apply intensity blending ─────────────────────────────
    # Blend between identity CDL (no change) and computed CDL
    slope = (
        _lerp(1.0, r_slope, intensity),
        _lerp(1.0, g_slope, intensity),
        _lerp(1.0, b_slope, intensity),
    )
    offset = (
        _lerp(0.0, r_offset, intensity),
        _lerp(0.0, g_offset, intensity),
        _lerp(0.0, b_offset, intensity),
    )
    power = (
        _lerp(1.0, r_power, intensity),
        _lerp(1.0, g_power, intensity),
        _lerp(1.0, b_power, intensity),
    )
    saturation = _lerp(1.0, sat_ratio, intensity)

    return {
        "slope": slope,
        "offset": offset,
        "power": power,
        "saturation": saturation,
    }


def combine_cdl(normalization_cdl: Dict, creative_cdl: Dict) -> Dict:
    """
    Combine normalization CDL and creative CDL into a single CDL.
    
    The normalization is applied first (exposure + WB correction),
    then the creative transform.
    
    Combined:
        slope_combined = slope_norm * slope_creative
        offset_combined = offset_norm * slope_creative + offset_creative
        power_combined = power_norm * power_creative
    """
    ns = normalization_cdl.get("slope", (1, 1, 1))
    no = normalization_cdl.get("offset", (0, 0, 0))
    np_ = normalization_cdl.get("power", (1, 1, 1))

    cs = creative_cdl.get("slope", (1, 1, 1))
    co = creative_cdl.get("offset", (0, 0, 0))
    cp = creative_cdl.get("power", (1, 1, 1))

    slope = tuple(_clamp(ns[i] * cs[i], 0.7, 1.5) for i in range(3))
    offset = tuple(_clamp(no[i] * cs[i] + co[i], -0.03, 0.03) for i in range(3))
    power = tuple(_clamp(np_[i] * cp[i], 0.8, 1.4) for i in range(3))

    # Use creative saturation (normalization doesn't change saturation)
    saturation = creative_cdl.get("saturation", 1.0)
    norm_sat = normalization_cdl.get("saturation", 1.0)
    saturation = _clamp(saturation * norm_sat, 0.0, 2.0)

    return {
        "slope": slope,
        "offset": offset,
        "power": power,
        "saturation": saturation,
    }


def cdl_for_look_profile(look_profile, source: ClipColorProfile) -> Dict:
    """
    Compute a combined CDL for a look profile applied to a source clip.
    
    This uses the look profile's explicit CDL adjustments AND computes
    additional corrections based on the difference between the source
    clip's stats and the look's target characteristics.
    """
    from color_engine.normalizer import compute_normalization_for_profile

    # Step 1: Normalization CDL (exposure + WB correction)
    norm_cdl = compute_normalization_for_profile(
        source,
        target_luminance=look_profile.target_luminance,
        target_temp=look_profile.target_temp,
    )

    # Step 2: Look profile's explicit CDL adjustments
    look_cdl = {
        "slope": look_profile.slope_adjust,
        "offset": look_profile.offset_adjust,
        "power": look_profile.power_adjust,
        "saturation": look_profile.saturation_multiplier,
    }

    # Step 3: Contrast adjustment via SLOPE (not power!)
    # Higher contrast → higher slope → stretches dynamic range
    # Power < 1 BRIGHTENS the image, which is wrong for contrast
    if look_profile.contrast != 1.0:
        contrast_factor = look_profile.contrast
        look_cdl["slope"] = tuple(
            s * contrast_factor for s in look_cdl["slope"]
        )

    # Step 4: Shadow lift via offset (keep very subtle)
    if look_profile.shadow_lift > 0:
        lift = min(look_profile.shadow_lift, 0.01)  # Hard cap at 0.01
        look_cdl["offset"] = tuple(
            o + lift for o in look_cdl["offset"]
        )

    # Step 5: Combine normalization + creative
    combined = combine_cdl(norm_cdl, look_cdl)

    return combined


def cdl_for_reference_match(
    source: ClipColorProfile,
    reference: ClipColorProfile,
    intensity: float = 1.0,
) -> Dict:
    """
    Compute CDL that matches a source clip to a reference clip.
    
    Combines normalization (bring source to reference's exposure/WB)
    with creative transfer (match color distribution).
    """
    from color_engine.normalizer import compute_normalization_for_profile

    # Step 1: Normalize toward reference's luminance and color temp
    norm_cdl = compute_normalization_for_profile(
        source,
        target_luminance=reference.luminance_mean,
        target_temp=reference.estimated_color_temp,
    )

    # Step 2: Creative transfer CDL
    creative_cdl = compute_creative_cdl(source, reference, intensity)

    # Step 3: Combine
    combined = combine_cdl(norm_cdl, creative_cdl)

    return combined


def format_cdl_for_resolve(cdl: Dict, node_index: int = 1) -> Dict:
    """
    Format a CDL dict into the structure expected by Resolve's SetCDL.
    
    Resolve expects space-separated string values in ASC CDL format,
    NOT nested dicts with Red/Green/Blue keys.
    """
    s = cdl["slope"]
    o = cdl["offset"]
    p = cdl["power"]

    return {
        "NodeIndex": str(node_index),
        "Slope": f"{float(s[0]):.4f} {float(s[1]):.4f} {float(s[2]):.4f}",
        "Offset": f"{float(o[0]):.4f} {float(o[1]):.4f} {float(o[2]):.4f}",
        "Power": f"{float(p[0]):.4f} {float(p[1]):.4f} {float(p[2]):.4f}",
        "Saturation": f"{float(cdl.get('saturation', 1.0)):.4f}",
    }


# ── Internal Helpers ─────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation: a + (b - a) * t"""
    return a + (b - a) * t


def _estimate_gamma(profile: ClipColorProfile) -> float:
    """
    Estimate the effective gamma of a clip from its luminance stats.
    Higher luminance_mean relative to midpoint suggests lower gamma.
    """
    lum = profile.luminance_mean if profile.luminance_mean else 0.45
    # Map luminance to approximate gamma
    # 0.5 luminance ≈ gamma 1.0, higher luminance = lower gamma
    if lum > 0.01:
        return 0.5 / max(lum, 0.01)
    return 1.0
