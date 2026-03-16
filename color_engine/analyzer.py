"""
ResolveAI – Color Analyzer

Extracts comprehensive color statistics from video frames for use
in color matching and look application.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

try:
    import cv2
except ImportError:
    cv2 = None

from config import HISTOGRAM_BINS, DOMINANT_COLORS_K


@dataclass
class ChannelStats:
    """Statistics for a single color channel."""
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    histogram: np.ndarray = field(default_factory=lambda: np.zeros(256))


@dataclass
class ClipColorProfile:
    """
    Complete color profile of a clip, derived from sampled frames.
    
    All values are normalized to 0–1 range internally for algorithm use.
    The raw histograms use 0–255 range.
    """
    clip_name: str = ""

    # Per-channel stats (in RGB order)
    red: ChannelStats = field(default_factory=ChannelStats)
    green: ChannelStats = field(default_factory=ChannelStats)
    blue: ChannelStats = field(default_factory=ChannelStats)

    # LAB color space stats (for Reinhard transfer)
    lab_l: ChannelStats = field(default_factory=ChannelStats)
    lab_a: ChannelStats = field(default_factory=ChannelStats)
    lab_b: ChannelStats = field(default_factory=ChannelStats)

    # Luminance
    luminance_mean: float = 0.0
    luminance_std: float = 0.0
    luminance_min: float = 0.0
    luminance_max: float = 0.0
    dynamic_range: float = 0.0       # max - min
    exposure_bias: float = 0.0       # How far from target luminance

    # Color temperature estimation
    estimated_color_temp: float = 6500.0   # In Kelvin
    warm_cool_ratio: float = 1.0           # > 1 = warm, < 1 = cool

    # Dominant colors (from K-means)
    dominant_colors: List[Tuple[int, int, int]] = field(default_factory=list)
    dominant_weights: List[float] = field(default_factory=list)

    # Overall saturation
    saturation_mean: float = 0.0
    saturation_std: float = 0.0

    # Covariance matrix (for MVGD transfer)
    rgb_covariance: Optional[np.ndarray] = None
    rgb_mean: Optional[np.ndarray] = None


def analyze_frames(frames: list, clip_name: str = "") -> ClipColorProfile:
    """
    Analyze a list of frames and return a comprehensive ClipColorProfile.
    
    Args:
        frames: List of numpy arrays in BGR format (from OpenCV).
        clip_name: Name of the clip for identification.
    
    Returns:
        ClipColorProfile with all color statistics populated.
    """
    if not frames:
        return ClipColorProfile(clip_name=clip_name)

    if cv2 is None:
        raise RuntimeError("OpenCV is required for color analysis.")

    profile = ClipColorProfile(clip_name=clip_name)

    # Stack all frames into one big array for global statistics
    # Convert BGR → RGB first
    rgb_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames]
    all_pixels_rgb = np.vstack([f.reshape(-1, 3) for f in rgb_frames]).astype(np.float64)

    # ── RGB Channel Statistics ───────────────────────────────
    profile.red = _compute_channel_stats(all_pixels_rgb[:, 0])
    profile.green = _compute_channel_stats(all_pixels_rgb[:, 1])
    profile.blue = _compute_channel_stats(all_pixels_rgb[:, 2])

    # ── RGB Mean & Covariance (for MVGD) ─────────────────────
    profile.rgb_mean = np.mean(all_pixels_rgb, axis=0)
    profile.rgb_covariance = np.cov(all_pixels_rgb.T)

    # ── LAB Color Space Statistics ───────────────────────────
    lab_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2LAB) for f in frames]
    all_pixels_lab = np.vstack([f.reshape(-1, 3) for f in lab_frames]).astype(np.float64)

    profile.lab_l = _compute_channel_stats(all_pixels_lab[:, 0])
    profile.lab_a = _compute_channel_stats(all_pixels_lab[:, 1])
    profile.lab_b = _compute_channel_stats(all_pixels_lab[:, 2])

    # ── Luminance ────────────────────────────────────────────
    # Use LAB L channel (0–255 in OpenCV's LAB, where L is 0–255 mapping of 0–100)
    profile.luminance_mean = profile.lab_l.mean / 255.0
    profile.luminance_std = profile.lab_l.std / 255.0
    profile.luminance_min = profile.lab_l.min_val / 255.0
    profile.luminance_max = profile.lab_l.max_val / 255.0
    profile.dynamic_range = profile.luminance_max - profile.luminance_min

    # ── HSV for Saturation ───────────────────────────────────
    hsv_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2HSV) for f in frames]
    all_pixels_hsv = np.vstack([f.reshape(-1, 3) for f in hsv_frames]).astype(np.float64)

    profile.saturation_mean = np.mean(all_pixels_hsv[:, 1]) / 255.0
    profile.saturation_std = np.std(all_pixels_hsv[:, 1]) / 255.0

    # ── Color Temperature Estimation ─────────────────────────
    profile.estimated_color_temp = _estimate_color_temperature(
        profile.red.mean, profile.green.mean, profile.blue.mean
    )
    profile.warm_cool_ratio = _compute_warm_cool_ratio(
        profile.red.mean, profile.blue.mean
    )

    # ── Dominant Colors via K-means ──────────────────────────
    dominant, weights = _extract_dominant_colors(
        all_pixels_rgb, k=DOMINANT_COLORS_K
    )
    profile.dominant_colors = dominant
    profile.dominant_weights = weights

    return profile


def _compute_channel_stats(values: np.ndarray) -> ChannelStats:
    """Compute statistics for a single channel's pixel values."""
    stats = ChannelStats()
    stats.mean = float(np.mean(values))
    stats.std = float(np.std(values))
    stats.median = float(np.median(values))
    stats.min_val = float(np.min(values))
    stats.max_val = float(np.max(values))

    # Histogram (always 256 bins for 0–255 range)
    stats.histogram, _ = np.histogram(values, bins=256, range=(0, 256))
    stats.histogram = stats.histogram.astype(np.float64)
    # Normalize histogram to sum to 1
    total = stats.histogram.sum()
    if total > 0:
        stats.histogram = stats.histogram / total

    return stats


def _estimate_color_temperature(r_mean: float, g_mean: float, b_mean: float) -> float:
    """
    Rough estimation of color temperature from RGB means.
    
    This is an approximation using the McCamy formula adapted for
    RGB ratios. Not scientifically precise but good enough for
    relative comparisons between clips.
    
    Returns:
        Estimated color temperature in Kelvin.
    """
    if r_mean == 0 or b_mean == 0:
        return 6500.0

    # Simple ratio-based estimation
    rb_ratio = r_mean / max(b_mean, 1.0)

    # Map ratio to temperature:
    # rb_ratio > 1.0 → warm (< 6500K)
    # rb_ratio < 1.0 → cool (> 6500K)
    # rb_ratio ≈ 1.0 → neutral (~6500K)
    if rb_ratio > 1.0:
        temp = 6500.0 - (rb_ratio - 1.0) * 2000.0
    else:
        temp = 6500.0 + (1.0 - rb_ratio) * 3000.0

    return max(2000.0, min(12000.0, temp))


def _compute_warm_cool_ratio(r_mean: float, b_mean: float) -> float:
    """Compute the warm/cool ratio (R/B balance). > 1.0 = warm."""
    if b_mean < 1.0:
        return 2.0
    return r_mean / b_mean


def _extract_dominant_colors(pixels: np.ndarray, k: int = 5) -> tuple:
    """
    Extract dominant colors using K-means clustering.
    
    Returns:
        Tuple of (dominant_colors, weights) where:
        - dominant_colors: list of (R, G, B) tuples
        - weights: list of floats (proportion of pixels in each cluster)
    """
    if cv2 is None or len(pixels) == 0:
        return [], []

    # Subsample for speed (K-means on full pixel set is slow)
    max_samples = 10000
    if len(pixels) > max_samples:
        indices = np.random.choice(len(pixels), max_samples, replace=False)
        samples = pixels[indices].astype(np.float32)
    else:
        samples = pixels.astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    try:
        _, labels, centers = cv2.kmeans(
            samples, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
        )
    except cv2.error:
        return [], []

    # Calculate cluster weights
    labels = labels.flatten()
    total = len(labels)
    colors = []
    weights = []

    for i in range(k):
        count = np.sum(labels == i)
        weight = count / total
        color = tuple(int(c) for c in centers[i])
        colors.append(color)
        weights.append(weight)

    # Sort by weight (most dominant first)
    paired = sorted(zip(weights, colors), reverse=True)
    weights = [w for w, c in paired]
    colors = [c for w, c in paired]

    return colors, weights


def print_profile_summary(profile: ClipColorProfile):
    """Print a human-readable summary of a clip's color profile."""
    print(f"\n  Color Profile: {profile.clip_name}")
    print(f"  {'─' * 45}")
    print(f"  Luminance: {profile.luminance_mean:.3f} "
          f"(range: {profile.luminance_min:.3f}–{profile.luminance_max:.3f})")
    print(f"  Dynamic Range: {profile.dynamic_range:.3f}")
    print(f"  Color Temp: ~{profile.estimated_color_temp:.0f}K "
          f"({'warm' if profile.warm_cool_ratio > 1.05 else 'cool' if profile.warm_cool_ratio < 0.95 else 'neutral'})")
    print(f"  Saturation: {profile.saturation_mean:.3f}")
    print(f"  RGB Means: R={profile.red.mean:.1f} "
          f"G={profile.green.mean:.1f} B={profile.blue.mean:.1f}")
    if profile.dominant_colors:
        print(f"  Dominant Colors:")
        for i, (color, weight) in enumerate(
            zip(profile.dominant_colors[:3], profile.dominant_weights[:3])
        ):
            print(f"    #{i+1}: RGB{color} ({weight*100:.1f}%)")
    print()
