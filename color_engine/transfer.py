"""
ResolveAI – Color Transfer Algorithms

Implements three color transfer methods for matching colors between clips:
1. Reinhard Color Transfer (LAB space, fast, reliable)
2. Histogram Matching (per-channel CDF alignment)
3. Multi-Variate Gaussian Distribution (MVGD) Transfer (full 3D color mapping)

Each method takes source and target color profiles and returns a transform
function that can be used by the LUT generator.
"""

import numpy as np
from typing import Callable, Tuple
from color_engine.analyzer import ClipColorProfile

try:
    import cv2
except ImportError:
    cv2 = None


# ═══════════════════════════════════════════════════════════════
# 1. REINHARD COLOR TRANSFER
# ═══════════════════════════════════════════════════════════════

def reinhard_transfer(
    source_profile: ClipColorProfile,
    target_profile: ClipColorProfile,
    intensity: float = 1.0,
) -> Callable:
    """
    Compute the Reinhard color transfer from source → target in LAB space.
    
    Based on "Color Transfer between Images" by Reinhard et al. (2001).
    Works by matching the mean and standard deviation of each LAB channel.
    
    Args:
        source_profile: Color profile of the clip to transform.
        target_profile: Color profile of the target/reference clip.
        intensity: Blend factor (0.0 = no change, 1.0 = full transfer).
    
    Returns:
        A function that transforms an RGB pixel (0–255) to the target color space.
    """
    # Compute per-channel scale and shift in LAB space
    # For each channel: output = (input - src_mean) * (tgt_std / src_std) + tgt_mean

    def safe_ratio(tgt_std, src_std):
        if src_std < 1e-6:
            return 1.0
        return tgt_std / src_std

    l_scale = safe_ratio(target_profile.lab_l.std, source_profile.lab_l.std)
    a_scale = safe_ratio(target_profile.lab_a.std, source_profile.lab_a.std)
    b_scale = safe_ratio(target_profile.lab_b.std, source_profile.lab_b.std)

    l_shift = target_profile.lab_l.mean - source_profile.lab_l.mean * l_scale
    a_shift = target_profile.lab_a.mean - source_profile.lab_a.mean * a_scale
    b_shift = target_profile.lab_b.mean - source_profile.lab_b.mean * b_scale

    # Apply intensity blending
    l_scale = 1.0 + (l_scale - 1.0) * intensity
    a_scale = 1.0 + (a_scale - 1.0) * intensity
    b_scale = 1.0 + (b_scale - 1.0) * intensity
    l_shift *= intensity
    a_shift *= intensity
    b_shift *= intensity

    def transform(rgb_pixel: np.ndarray) -> np.ndarray:
        """
        Transform a single RGB pixel (0–255 uint8 or float).
        
        For LUT generation, this is called for each point in the 3D grid.
        """
        # RGB → LAB via OpenCV
        pixel_bgr = np.array([[[rgb_pixel[2], rgb_pixel[1], rgb_pixel[0]]]],
                             dtype=np.uint8)
        pixel_lab = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2LAB).astype(np.float64)[0, 0]

        # Apply transfer
        pixel_lab[0] = pixel_lab[0] * l_scale + l_shift
        pixel_lab[1] = pixel_lab[1] * a_scale + a_shift
        pixel_lab[2] = pixel_lab[2] * b_scale + b_shift

        # Clamp to valid LAB range
        pixel_lab[0] = np.clip(pixel_lab[0], 0, 255)
        pixel_lab[1] = np.clip(pixel_lab[1], 0, 255)
        pixel_lab[2] = np.clip(pixel_lab[2], 0, 255)

        # LAB → RGB
        result_bgr = cv2.cvtColor(
            pixel_lab.reshape(1, 1, 3).astype(np.uint8),
            cv2.COLOR_LAB2BGR
        )[0, 0]

        return np.array([result_bgr[2], result_bgr[1], result_bgr[0]], dtype=np.float64)

    return transform


def reinhard_transfer_image(
    source_image: np.ndarray,
    source_profile: ClipColorProfile,
    target_profile: ClipColorProfile,
    intensity: float = 1.0,
) -> np.ndarray:
    """
    Apply Reinhard transfer to an entire image (faster than per-pixel for preview).
    
    Args:
        source_image: BGR image (from OpenCV).
        source_profile: Source clip's color profile.
        target_profile: Target clip's color profile.
        intensity: Blend factor (0–1).
    
    Returns:
        Transformed BGR image.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV required")

    # Convert to LAB (float for precision)
    lab = cv2.cvtColor(source_image, cv2.COLOR_BGR2LAB).astype(np.float64)

    def safe_ratio(tgt, src):
        return tgt / src if src > 1e-6 else 1.0

    # Apply per-channel transfer
    for ch, (src_stats, tgt_stats) in enumerate([
        (source_profile.lab_l, target_profile.lab_l),
        (source_profile.lab_a, target_profile.lab_a),
        (source_profile.lab_b, target_profile.lab_b),
    ]):
        scale = safe_ratio(tgt_stats.std, src_stats.std)
        scale = 1.0 + (scale - 1.0) * intensity

        lab[:, :, ch] = (lab[:, :, ch] - src_stats.mean) * scale + tgt_stats.mean * intensity + src_stats.mean * (1.0 - intensity)

    lab = np.clip(lab, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


# ═══════════════════════════════════════════════════════════════
# 2. HISTOGRAM MATCHING
# ═══════════════════════════════════════════════════════════════

def histogram_match_transfer(
    source_profile: ClipColorProfile,
    target_profile: ClipColorProfile,
    intensity: float = 1.0,
) -> Callable:
    """
    Compute a per-channel histogram matching transfer.
    
    Creates 1D lookup tables for each RGB channel that remap the source
    histogram CDF to match the target histogram CDF.
    
    Args:
        source_profile: Source clip's profile.
        target_profile: Target clip's profile.
        intensity: Blend factor (0–1).
    
    Returns:
        Transform function for RGB pixels.
    """
    # Build per-channel 1D LUTs via CDF matching
    r_lut = _build_histogram_lut(source_profile.red.histogram,
                                  target_profile.red.histogram)
    g_lut = _build_histogram_lut(source_profile.green.histogram,
                                  target_profile.green.histogram)
    b_lut = _build_histogram_lut(source_profile.blue.histogram,
                                  target_profile.blue.histogram)

    def transform(rgb_pixel: np.ndarray) -> np.ndarray:
        r = int(np.clip(rgb_pixel[0], 0, 255))
        g = int(np.clip(rgb_pixel[1], 0, 255))
        b = int(np.clip(rgb_pixel[2], 0, 255))

        # Look up new values
        new_r = r_lut[r] * intensity + r * (1.0 - intensity)
        new_g = g_lut[g] * intensity + g * (1.0 - intensity)
        new_b = b_lut[b] * intensity + b * (1.0 - intensity)

        return np.array([new_r, new_g, new_b], dtype=np.float64)

    return transform


def _build_histogram_lut(source_hist: np.ndarray, target_hist: np.ndarray) -> np.ndarray:
    """
    Build a 256-entry lookup table that maps source intensities to target intensities
    using CDF matching.
    """
    # Compute CDFs
    src_cdf = np.cumsum(source_hist)
    tgt_cdf = np.cumsum(target_hist)

    # Normalize CDFs to 0–1
    if src_cdf[-1] > 0:
        src_cdf = src_cdf / src_cdf[-1]
    if tgt_cdf[-1] > 0:
        tgt_cdf = tgt_cdf / tgt_cdf[-1]

    # For each source intensity level, find the target intensity
    # whose CDF value most closely matches
    lut = np.zeros(256, dtype=np.float64)
    for i in range(256):
        # Find where src_cdf[i] falls in tgt_cdf
        idx = np.searchsorted(tgt_cdf, src_cdf[i])
        lut[i] = min(idx, 255)

    return lut


# ═══════════════════════════════════════════════════════════════
# 3. MVGD (MULTI-VARIATE GAUSSIAN DISTRIBUTION) TRANSFER
# ═══════════════════════════════════════════════════════════════

def mvgd_transfer(
    source_profile: ClipColorProfile,
    target_profile: ClipColorProfile,
    intensity: float = 1.0,
) -> Callable:
    """
    Compute a Multi-Variate Gaussian Distribution color transfer.
    
    This is a more sophisticated approach that considers correlations
    between color channels. It models each image's color distribution as
    a 3D Gaussian and computes a linear transform to match them.
    
    The transform is: output = T @ (input - src_mean) + tgt_mean
    where T = tgt_cov_sqrt @ src_cov_sqrt_inv
    
    Args:
        source_profile: Source clip's profile (must have rgb_covariance).
        target_profile: Target clip's profile (must have rgb_covariance).
        intensity: Blend factor (0–1).
    
    Returns:
        Transform function for RGB pixels.
    """
    src_mean = source_profile.rgb_mean
    tgt_mean = target_profile.rgb_mean
    src_cov = source_profile.rgb_covariance
    tgt_cov = target_profile.rgb_covariance

    if src_mean is None or tgt_mean is None or src_cov is None or tgt_cov is None:
        # Fall back to Reinhard if covariance data isn't available
        return reinhard_transfer(source_profile, target_profile, intensity)

    # Compute matrix square roots
    src_cov_sqrt = _matrix_sqrt(src_cov)
    tgt_cov_sqrt = _matrix_sqrt(tgt_cov)

    # Compute inverse of source sqrt
    try:
        src_cov_sqrt_inv = np.linalg.inv(src_cov_sqrt)
    except np.linalg.LinAlgError:
        # Singular matrix – fall back to Reinhard
        return reinhard_transfer(source_profile, target_profile, intensity)

    # Transfer matrix
    T = tgt_cov_sqrt @ src_cov_sqrt_inv

    # Blend with identity matrix for intensity control
    I = np.eye(3)
    T_blended = I + (T - I) * intensity
    mean_shift = (tgt_mean - src_mean) * intensity

    def transform(rgb_pixel: np.ndarray) -> np.ndarray:
        centered = rgb_pixel.astype(np.float64) - src_mean
        result = T_blended @ centered + src_mean + mean_shift
        return np.clip(result, 0, 255)

    return transform


def _matrix_sqrt(matrix: np.ndarray) -> np.ndarray:
    """
    Compute the matrix square root via eigenvalue decomposition.
    
    For a symmetric positive semi-definite matrix M:
    M_sqrt = V @ diag(sqrt(eigenvalues)) @ V^T
    """
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    # Clamp negative eigenvalues (numerical noise)
    eigenvalues = np.maximum(eigenvalues, 0)
    sqrt_eigenvalues = np.sqrt(eigenvalues)
    return eigenvectors @ np.diag(sqrt_eigenvalues) @ eigenvectors.T


# ═══════════════════════════════════════════════════════════════
# FACTORY: Get transfer function by name
# ═══════════════════════════════════════════════════════════════

TRANSFER_METHODS = {
    "reinhard": reinhard_transfer,
    "histogram": histogram_match_transfer,
    "mvgd": mvgd_transfer,
}


def get_transfer_function(
    method: str,
    source_profile: ClipColorProfile,
    target_profile: ClipColorProfile,
    intensity: float = 1.0,
) -> Callable:
    """
    Get a color transfer function by method name.
    
    Args:
        method: One of "reinhard", "histogram", "mvgd".
        source_profile: Source clip's color profile.
        target_profile: Target/reference clip's color profile.
        intensity: Blend factor (0–1).
    
    Returns:
        A transform function: f(rgb_pixel) → rgb_pixel
    """
    if method not in TRANSFER_METHODS:
        raise ValueError(f"Unknown transfer method: {method}. "
                         f"Choose from: {list(TRANSFER_METHODS.keys())}")

    return TRANSFER_METHODS[method](source_profile, target_profile, intensity)
